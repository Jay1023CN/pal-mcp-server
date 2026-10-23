from __future__ import annotations

import json
import subprocess
import threading
import uuid
from collections import deque

from .common import BridgeError, workspace_path
from .discovery import qoder_command


class ACP:
    kind = "acp-stdio"

    def __init__(self, name, config=None):
        self.name, self.config = name, config or {}
        self.process = None
        self.info = None
        self.pending = {}
        self.sessions_data = {}
        self.permissions_data = {}
        self.lock = threading.RLock()
        self.write_lock = threading.Lock()
        self.start_lock = threading.Lock()
        self.counter = 0

    def connect(self):
        with self.start_lock:
            if self.process and self.process.poll() is None:
                return {"connected": True, "transport": self.kind, "agent": self.info.get("agentInfo")}
            command = qoder_command(self.name, self.config)
            self.process = subprocess.Popen(
                [*command, "--acp"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.reader_thread = threading.Thread(target=self._reader, args=(self.process,), daemon=True)
            self.stderr_thread = threading.Thread(target=self._drain_stderr, args=(self.process,), daemon=True)
            self.reader_thread.start()
            self.stderr_thread.start()
            self.info = self.call(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False},
                    "clientInfo": {"name": "agent-link-mcp", "version": "0.1.0"},
                },
            )
            return {
                "connected": True,
                "transport": self.kind,
                "agent": self.info.get("agentInfo"),
                "note": "ACP agent process; this does not control an existing IDE chat.",
            }

    def _write(self, value):
        with self.write_lock:
            if not self.process or self.process.poll() is not None:
                raise BridgeError(f"{self.name} ACP process is not running.")
            self.process.stdin.write(json.dumps(value, ensure_ascii=False) + "\n")
            self.process.stdin.flush()

    def call(self, method, params, timeout=30):
        with self.lock:
            self.counter += 1
            identifier = self.counter
            item = {"event": threading.Event()}
            self.pending[identifier] = item
        try:
            self._write({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params})
            if not item["event"].wait(timeout):
                raise BridgeError(f"{method} timed out; outcome unknown. Do not resend automatically.")
            response = item["response"]
            if "error" in response:
                error = response["error"]
                # Agent protocol errors can contain upstream credentials; code only.
                raise BridgeError(
                    f'{self.name} {method} failed (ACP {error.get("code")}). Check login and account eligibility.'
                )
            return response.get("result", {})
        finally:
            with self.lock:
                self.pending.pop(identifier, None)

    def _reader(self, process):
        try:
            for line in process.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if "method" in message:
                    if "id" in message:
                        self._request(message)
                    elif message["method"] == "session/update":
                        self._update(message.get("params", {}))
                else:
                    with self.lock:
                        item = self.pending.get(message.get("id"))
                        if item:
                            item["response"] = message
                            item["event"].set()
        finally:
            with self.lock:
                for item in self.pending.values():
                    item["response"] = {"error": {"code": -32000}}
                    item["event"].set()

    @staticmethod
    def _drain_stderr(process):
        # Drain pipes to avoid blocking, but never log authentication or provider output.
        for _ in process.stderr:
            pass

    def _request(self, message):
        if message["method"] != "session/request_permission":
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {"code": -32601, "message": "Unsupported client capability"},
                }
            )
            return
        params = message.get("params", {})
        key = str(uuid.uuid4())
        with self.lock:
            self.permissions_data[key] = {
                "rpc_id": message["id"],
                "session_id": params.get("sessionId"),
                "tool": params.get("toolCall", {}),
                "options": params.get("options", []),
            }

    def _update(self, params):
        with self.lock:
            state = self.sessions_data.get(params.get("sessionId"))
            if state is None:
                return
            update = params.get("update", {})
            kind = update.get("sessionUpdate")
            if kind == "agent_message_chunk":
                content = update.get("content", {})
                if content.get("type") == "text":
                    state["text"] += content.get("text", "")
            elif kind in ("tool_call", "tool_call_update"):
                state["events"].append(
                    {
                        "type": kind,
                        "title": update.get("title"),
                        "status": update.get("status"),
                        "tool_call_id": update.get("toolCallId"),
                    }
                )
            elif kind in ("current_mode_update", "config_option_update"):
                state["events"].append(update)

    def create(self, workspace, title="Agent Link", model=None):
        self.connect()
        path = str(workspace_path(workspace))
        result = self.call("session/new", {"cwd": path, "mcpServers": []})
        sid = result["sessionId"]
        with self.lock:
            self.sessions_data[sid] = {
                "id": sid,
                "title": title,
                "workspace": path,
                "status": "idle",
                "text": "",
                "events": deque(maxlen=200),
                "details": result,
                "done": threading.Event(),
            }
            self.sessions_data[sid]["done"].set()
        if model:
            self.call("session/set_model", {"sessionId": sid, "modelId": model})
        return {"id": sid, "details": result}

    def sessions(self, limit=30):
        with self.lock:
            return [
                {"id": s["id"], "title": s["title"], "workspace": s["workspace"], "status": s["status"]}
                for s in list(self.sessions_data.values())[-limit:]
            ]

    def models(self):
        with self.lock:
            return [s["details"].get("models", {}) for s in self.sessions_data.values()][-1:]

    def send(self, session_id, prompt):
        if not prompt.strip():
            raise BridgeError("prompt cannot be empty.")
        with self.lock:
            state = self.sessions_data.get(session_id)
            if not state:
                raise BridgeError("Session is not loaded in this MCP process; create a session first.")
            if state["status"] in ("running", "waiting_permission"):
                raise BridgeError("Session is busy.")
            state.update(status="running", text="", error=None, result=None)
            state["events"].clear()
            state["done"].clear()

        def run():
            try:
                result = self.call(
                    "session/prompt",
                    {"sessionId": session_id, "prompt": [{"type": "text", "text": prompt}]},
                    timeout=600,
                )
                with self.lock:
                    state["result"] = result
                    state["status"] = "completed" if result.get("stopReason") == "end_turn" else "stopped"
                    if not state["text"].strip() and not state["events"]:
                        state["status"] = "empty_response"
            except Exception as exc:
                with self.lock:
                    state["status"], state["error"] = "failed", str(exc)
            finally:
                with self.lock:
                    stale = [key for key, p in self.permissions_data.items() if p["session_id"] == session_id]
                    for key in stale:
                        permission = self.permissions_data.pop(key)
                        try:
                            self._write(
                                {
                                    "jsonrpc": "2.0",
                                    "id": permission["rpc_id"],
                                    "result": {"outcome": {"outcome": "cancelled"}},
                                }
                            )
                        except BridgeError:
                            pass
                state["done"].set()

        threading.Thread(target=run, daemon=True).start()
        return {"submitted": True, "session_id": session_id}

    def read(self, session_id, limit=20):
        with self.lock:
            state = self.sessions_data.get(session_id)
            if not state:
                raise BridgeError("Unknown session in this MCP process.")
            permissions = self.permissions(session_id)
            return {
                "session_id": session_id,
                "status": "waiting_permission" if permissions else state["status"],
                "text": state["text"],
                "error": state.get("error"),
                "events": list(state["events"])[-limit:],
                "result": state.get("result"),
                "permissions": permissions,
            }

    def wait(self, session_id, seconds=30):
        with self.lock:
            if session_id not in self.sessions_data:
                raise BridgeError("Unknown session.")
            done = self.sessions_data[session_id]["done"]
        # Return quickly if a permission request needs attention.
        for _ in range(max(1, min(int(seconds), 45))):
            if done.wait(1) or self.permissions(session_id):
                break
        return self.read(session_id)

    def permissions(self, session_id):
        with self.lock:
            return [
                {"id": k, "session_id": p["session_id"], "tool": p["tool"], "options": p["options"]}
                for k, p in self.permissions_data.items()
                if p["session_id"] == session_id
            ]

    def reply(self, permission_id, option_id=None):
        with self.lock:
            permission = self.permissions_data.get(permission_id)
            if not permission:
                raise BridgeError("Permission request expired or not found.")
            if option_id and option_id not in [o.get("optionId") for o in permission["options"]]:
                raise BridgeError("Unknown permission option.")
            outcome = {"outcome": "selected", "optionId": option_id} if option_id else {"outcome": "cancelled"}
            self._write({"jsonrpc": "2.0", "id": permission["rpc_id"], "result": {"outcome": outcome}})
            self.permissions_data.pop(permission_id)
            return {"replied": True}

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.process:
            for thread in (getattr(self, "reader_thread", None), getattr(self, "stderr_thread", None)):
                if thread:
                    thread.join(timeout=2)
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                if stream:
                    stream.close()
