# 命令系统

## 📚 命令系统

### 主命令行选项

`illusion` 主命令支持以下选项，按功能分组：

#### Session（会话）

| 选项 | 简写 | 说明 |
|------|------|------|
| `--continue` | `-c` | 继续当前目录的最近一次会话 |
| `--resume [SESSION_ID]` | `-r` | 通过会话 ID 恢复会话；不传值则打开选择器 |
| `--name <NAME>` | `-n` | 为本次会话设置显示名称（存入 `tool_metadata.session_name`） |

#### Model & Effort（模型与推理强度）

| 选项 | 简写 | 说明 |
|------|------|------|
| `--model <MODEL>` | `-m` | 模型别名（如 `sonnet`、`opus`）或完整模型 ID（如 `env_1.model_2`） |
| `--effort <LEVEL>` | - | 推理强度级别：`low` / `medium` / `high` / `max` |
| `--verbose` | - | 覆盖配置中的详细输出设置，启用 INFO 级别日志 |
| `--max-turns <N>` | - | 最大代理轮次数（与 `--print` 配合使用尤其有用） |

#### Output（输出）

| 选项 | 简写 | 说明 |
|------|------|------|
| `--print <PROMPT>` | `-p` | 非交互式打印模式：执行单次提示词后退出 |
| `--output-format <FORMAT>` | - | `--print` 模式的输出格式：`text`（默认）/ `json` / `stream-json` |

#### Permissions（权限）

| 选项 | 说明 |
|------|------|
| `--permission-mode <MODE>` | 权限模式：`default` / `plan` / `full_auto` |
| `--dangerously-skip-permissions` | 跳过所有权限检查（等价于 `--permission-mode full_auto`，仅适用于沙箱环境） |
| `--allowed-tools <TOOLS...>` | 工具白名单（空格或逗号分隔），仅保留指定工具 |
| `--disallowed-tools <TOOLS...>` | 工具黑名单（空格或逗号分隔），移除指定工具 |

#### System & Context（系统与上下文）

| 选项 | 简写 | 说明 |
|------|------|------|
| `--system-prompt <PROMPT>` | `-s` | 完全覆盖默认系统提示词 |
| `--append-system-prompt <TEXT>` | - | 在默认系统提示词末尾追加内容（不覆盖原提示词） |
| `--settings <PATH_OR_JSON>` | - | 指定 JSON 设置文件路径或内联 JSON 字符串 |
| `--base-url <URL>` | - | Anthropic 兼容 API 基础 URL |
| `--api-key <KEY>` | `-k` | API 密钥（覆盖配置和环境变量） |
| `--bare` | - | 最小模式：跳过 hooks、plugins、MCP 自动发现 |
| `--api-format <FORMAT>` | - | API 格式：`anthropic`（默认）或 `openai`（DashScope、GitHub Models 等） |

#### Advanced（高级）

| 选项 | 简写 | 说明 |
|------|------|------|
| `--debug` | `-d` | 启用 DEBUG 级别日志 |
| `--mcp-config <CONFIG...>` | - | 从 JSON 文件或字符串加载额外 MCP 服务器（可多次指定） |

#### 全局

| 选项 | 简写 | 说明 |
|------|------|------|
| `--version` | `-v` | 显示版本号并退出 |
| `--help` | `-h` | 显示帮助信息并退出 |

### 运行模式

`illusion` 支持三种主要运行模式：

#### 1. 交互式会话模式（默认）

```bash
illusion                            # 启动交互式会话
illusion -m env_1.model_2           # 指定模型启动
illusion --permission-mode full_auto  # 以自动权限模式启动
illusion --verbose                  # 详细日志启动
illusion --bare                     # 最小模式启动（无插件/MCP/hooks）
```

#### 2. 非交互式打印模式

```bash
illusion -p "帮我分析这个项目的结构"
illusion -p "say hi" --output-format json
illusion -p "refactor this" --max-turns 10
```

#### 3. 会话恢复模式

```bash
illusion -c                         # 继续最近会话
illusion --resume                   # 打开会话选择器
illusion --resume <session-id>      # 恢复指定会话
illusion -c --name "feature-work"   # 继续会话并命名
```

### 参数透传

所有主命令选项都会完整透传到 React 终端前端（`launch_react_tui` → `build_backend_command`）和结构化后端主机（`run_backend_host` → `build_runtime`），确保在交互式模式、`--backend-only` 子进程模式、`-c`/`--resume` 会话恢复模式下均生效。

### 常见组合示例

```bash
# 指定模型 + 权限模式 + 追加系统提示词
illusion -m env_1.model_2 --permission-mode plan --append-system-prompt "Always respond in Chinese"

# 最小模式 + 额外 MCP 配置
illusion --bare --mcp-config '{"mcpServers": {"my-server": {"type": "stdio", "command": "node", "args": ["server.js"]}}}'

# 工具白名单（仅允许 bash 和文件读取）
illusion --allowed-tools bash read_file

# 工具黑名单（禁用 bash 和 powershell）
illusion --disallowed-tools bash powershell

# 自定义设置文件 + API 格式
illusion --settings /path/to/custom.json --api-format openai

# 调试模式 + 详细日志
illusion --debug --verbose

# 为会话命名
illusion --name "debug-auth-issue"
```

### `--mcp-config` 格式说明

`--mcp-config` 接受两种输入形式：

**JSON 字符串**（支持单服务器或多服务器格式）：

```bash
# 多服务器格式
illusion --mcp-config '{"mcpServers": {"server1": {"type": "stdio", "command": "node", "args": ["s1.js"]}, "server2": {"type": "stdio", "command": "python", "args": ["s2.py"]}}}'

# 单服务器格式
illusion --mcp-config '{"type": "stdio", "command": "node", "args": ["server.js"]}'

# 也支持 snake_case 键
illusion --mcp-config '{"mcp_servers": {"my-server": {...}}}'
```

**JSON 文件路径**（路径存在时自动读取文件）：

```bash
illusion --mcp-config /path/to/mcp-servers.json
```

可多次指定 `--mcp-config` 以加载多个配置源。与 `--bare` 模式兼容：`--bare` 跳过自动发现的 MCP 服务器，但 `--mcp-config` 显式指定的服务器仍会加载。

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
