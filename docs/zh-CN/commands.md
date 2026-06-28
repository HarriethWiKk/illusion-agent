# 命令系统

## 📚 命令系统

### 子命令

```bash
# Web UI
illusion web                     # 启动 Web UI 浏览器界面（默认端口 3000）
illusion web --port 8080         # 自定义端口启动

# 认证管理
illusion auth login              # 交互式配置提供商（自定义/Anthropic/OpenAI/Copilot/Codex）
illusion auth status             # 查看所有环境的认证状态
illusion auth logout [env_N]     # 清除环境凭据
illusion auth switch [env_N]     # 切换活动环境
illusion auth add-model <env_N> <model_name>  # 向已有环境添加模型

# MCP 管理
illusion mcp list                # 列出 MCP 服务器
illusion mcp add <name> <config> # 添加服务器
illusion mcp remove <name>       # 移除服务器

# 插件管理
illusion plugin list             # 列出插件
illusion plugin install <source> # 安装插件
illusion plugin uninstall <name> # 卸载插件

# 渠道管理（飞书/微信/QQ 消息渠道）
illusion channel login           # 交互式配置渠道（选择渠道 → 配置凭据）
illusion channel serve           # 前台运行渠道守护进程（监听消息）
illusion channel status          # 查看渠道状态（启用/连接/PID）
illusion channel enable feishu   # 启用飞书渠道
illusion channel disable feishu  # 禁用飞书渠道
illusion channel logout feishu   # 清除飞书渠道凭据

# 定时任务
illusion cron start              # 启动调度器
illusion cron stop               # 停止调度器
illusion cron status             # 查看状态
illusion cron list               # 列出任务
illusion cron toggle <name> <true|false>  # 启用/禁用任务
illusion cron run <name>         # 手动触发执行任务
illusion cron history            # 查看执行历史
illusion cron logs               # 查看调度器日志

# 自更新
illusion update                  # 检查并从 PyPI 安装更新
illusion update --deps           # 同时更新项目依赖
```

### 交互式斜杠命令

在交互式会话中，可使用以下命令：

| 类别 | 命令示例 | 说明 |
|------|----------|------|
| 会话管理 | `/help`, `/clear`, `/exit`, `/rewind`, `/delete` | 管理会话状态 |
| 记忆快照 | `/memory`, `/resume`, `/export`, `/rules` | 记忆与会话管理 |
| 配置设置 | `/config`, `/model`, `/permissions`, `/plan`, `/thinking` | 调整运行配置 |
| 插件扩展 | `/skills`, `/hooks`, `/mcp`, `/plugin` | 管理扩展功能 |
| 项目 Git | `/init`, `/diff`, `/branch`, `/commit` | 项目与版本控制 |
| 多智能体 | `/continue` | Agent 协作 |
| 自更新 | `/update` | 检查并安装 IllusionCode 更新 |
