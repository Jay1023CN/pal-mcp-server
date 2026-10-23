# PAL Agent Link

**让不同的编码代理在同一个项目里协作。**

基于 [PAL MCP Server](https://github.com/BeehiveInnovations/pal-mcp-server) 二次开发，通过 MCP 把任务交给 Antigravity、OpenCode、Qoder、Qoder CN 和 WorkBuddy，读取会话输出并继续跟进。保留上游 `clink`，可调用 Codex CLI、Claude Code 和 Gemini CLI；也保留 PAL 原有的模型分析与审查工具。

[![Agent Link tests](https://github.com/Jay1023CN/pal-mcp-server/actions/workflows/agent-link.yml/badge.svg)](https://github.com/Jay1023CN/pal-mcp-server/actions/workflows/agent-link.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

[安装与配置](docs/agent-link.md) · [验证记录](docs/agent-link-release.md) · [上游 PAL 文档](README.upstream.md) · [反馈问题](https://github.com/Jay1023CN/pal-mcp-server/issues)

## 能接哪些客户端

| 客户端 | 接入方式 | 当前验证 |
| --- | --- | --- |
| Antigravity | 桌面本地 RPC，连接桌面会话 | 已验证消息往返和临时文件写入 |
| OpenCode | 本机 HTTP 服务，适配 1.x / 2.x | 已验证 2.x 真实消息往返；1.x 待实测 |
| Qoder | 官方 ACP CLI 代理 | 已验证真实消息往返 |
| Qoder CN | 国内版独立 ACP CLI 代理 | 已验证真实消息往返 |
| WorkBuddy | 官方本地助理 Open API | 契约测试通过，真实 OAuth 联调待完成 |
| Codex CLI / Claude Code / Gemini CLI | 上游 `clink` | 保留上游实现，未在本分支逐项重新验收 |

Antigravity 接的是桌面程序的会话后端，不需要桌面点击，也不会回退到无界面的 Antigravity CLI。Qoder 和 Qoder CN 目前通过 ACP 启动代理进程，不接管 IDE 中已有的聊天窗口。WorkBuddy 需要官方 OAuth 授权和在线的本地助理。

## 快速开始

需要 **Python 3.10+**，以及你要调用的客户端或 CLI。先在对应客户端完成登录；各代理可以单独使用，不必全部安装。

```sh
git clone https://github.com/Jay1023CN/pal-mcp-server.git
cd pal-mcp-server
python -m venv .venv
```

激活虚拟环境：

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```sh
# macOS / Linux
source .venv/bin/activate
```

安装并检查连接：

```sh
python -m pip install .
pal-agent-link --check
```

在支持 stdio MCP 的客户端中添加：

```json
{
  "mcpServers": {
    "pal-agent-link": {
      "command": "pal-mcp-server",
      "env": {
        "PAL_AGENT_ONLY": "1",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

如果 MCP 客户端找不到这个命令，把 `command` 换成虚拟环境里 `pal-mcp-server` 的绝对路径：Windows 位于 `.venv/Scripts/`，macOS / Linux 位于 `.venv/bin/`。客户端通常不会继承终端中刚激活的虚拟环境。

`PAL_AGENT_ONLY=1` 启用代理模式，不需要 PAL 的模型供应商 API Key；被调用的客户端仍需具备自己的登录态和可用模型。移除该变量并按[上游说明](README.upstream.md)配置供应商，即可使用完整 PAL 工具。当前 fork 尚未发布到 PyPI，请从本仓库安装。

## 怎样协作

向 MCP 客户端提出任务，例如：

> 检查当前可用的编码代理。让 Qoder 检查后端接口，让 OpenCode 检查前端调用，各自提交问题清单。先不要改文件，最后汇总两边结果。

客户端可通过 PAL 原生工具 `agentlink` 完成以下步骤：

| action | 用途 |
| --- | --- |
| `status` | 检查可用连接 |
| `sessions` / `models` | 查询目标代理的会话或模型 |
| `create` | 为指定工作目录创建会话 |
| `send` | 提交任务或继续对话 |
| `read` / `wait` | 读取输出、等待进展 |
| `permissions` / `permission_reply` | 查看和回答 ACP 权限请求 |

例如查询连接：

```json
{"action": "status"}
```

创建 Qoder 会话，`workspace` 填你自己机器上已存在的绝对目录：

```json
{"action": "create", "agent": "qoder", "workspace": "/absolute/path/to/project"}
```

后续使用返回的 `session_id` 提交任务并读取结果。通过 PAL 工具指定目标模型时，参数名是 `agent_model`。若使用独立的 `pal-agent-link` 入口，则会暴露多项 `agent_*` 工具；两种入口的参数见[详细说明](docs/agent-link.md)。

任务被接收不代表已经完成，需继续读取状态和输出。多个代理写代码时要划分文件范围；当前版本不提供自动分工、文件锁或冲突合并。ACP 会话保存在当前 MCP 进程内，重启后暂不自动恢复。

## 配置与兼容性

默认从标准用户目录、PATH 和本机进程发现客户端，不绑定开发者的用户名、盘符或固定服务端口。特殊安装可通过 `AGENT_LINK_CONFIG` 指定 JSON 配置；WorkBuddy 通过 `WORKBUDDY_ACCESS_TOKEN` 提供授权。完整配置见[接入说明](docs/agent-link.md#自动发现与可选配置)。

真实客户端验证目前在 Windows 上完成。Linux、macOS 和 Windows 的 Python 3.10 / 3.12 契约测试已通过 [GitHub Actions](https://github.com/Jay1023CN/pal-mcp-server/actions/workflows/agent-link.yml)，不等同于这些系统上的真实客户端验收。Antigravity 内部 RPC 和 OpenCode 实验接口可能随客户端版本变化。

## 开发与反馈

```sh
python -m pip install -e .
python -m pip install -r requirements-dev.txt
python -m pytest tests/test_agentlink_contracts.py tests/test_agentlink_tool.py -q
```

新增 15 项测试覆盖适配器契约、工具参数、ACP 权限和 HTTP 请求边界。此前的 12 项路径及 shell 测试失败已修复；本机非 integration 测试为 883 项通过、4 项跳过、0 项失败，另有 16 项 integration 测试未运行。详情见[验证记录](docs/agent-link-release.md)。

反馈时请提供操作系统、客户端版本、接入方式和错误信息。问题提交到[本 fork 的 Issues](https://github.com/Jay1023CN/pal-mcp-server/issues)；不要附上 token、登录配置或私人会话。

## 上游与许可

本项目是 [BeehiveInnovations/pal-mcp-server](https://github.com/BeehiveInnovations/pal-mcp-server) 的非官方 fork，使用 [Apache-2.0](LICENSE) 许可证，保留上游版权与原有工具。

本分支新增代码主要位于 `agent_link/` 和 `tools/agentlink.py`。上游 README 保存在 [README.upstream.md](README.upstream.md)，方便查阅原有 PAL 功能。项目与上述客户端厂商无隶属关系。
