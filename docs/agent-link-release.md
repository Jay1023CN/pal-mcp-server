# Agent Link 首版更新

本分支基于 BeehiveInnovations/pal-mcp-server 二次开发，保留上游 Apache-2.0 许可证。

- 新增 PAL 原生 `agentlink` 工具，统一查询连接、创建会话、提交任务、读取结果和处理 ACP 权限请求。
- 接入 Antigravity 桌面会话、OpenCode 服务、Qoder / Qoder CN ACP 和 WorkBuddy 官方本地助理 API。
- 增加 `PAL_AGENT_ONLY=1` 模式，无需配置模型供应商 API Key 即可启动代理工具。
- 自动发现标准安装目录和本机服务；源码不绑定个人目录，也不包含登录凭据。

## 本地验证

验证环境为 Windows。新增的 15 项契约和工具测试全部通过。通过 PAL 原生 MCP 工具完成 OpenCode、Qoder 的真实消息往返；独立桥接入口也完成了 Qoder CN 的真实消息往返。Antigravity 已在此前的桌面会话接入中完成消息及临时文件写入验证。

GitHub Actions 的 6 组契约测试已通过：Windows、Linux、macOS，分别使用 Python 3.10 和 3.12。[运行记录](https://github.com/Jay1023CN/pal-mcp-server/actions/runs/39898251199)。这些测试使用本地协议桩，不调用真实账号。

WorkBuddy 尚缺真实 OAuth 凭据和在线客户端，目前仅通过接口契约测试。Linux/macOS 尚未验证真实客户端。

PAL 非 integration 测试结果：869 通过、4 跳过、12 失败。失败集中在上游 Windows 路径判断及 shell 环境检测；最初的上游基线检查已在路径测试处失败。新增测试无失败，不将整套测试标为通过。
