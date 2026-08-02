# 项目架构

## 🏗️ 项目架构

```
illusion-agent/
├── src/illusion/           # 主要源代码
│   ├── api/                # API 客户端 (Anthropic, OpenAI 等)
│   ├── auth/               # 认证管理
│   ├── commands/           # 斜杠命令系统
│   ├── config/             # 配置系统
│   ├── coordinator/        # 多智能体协调器
│   ├── engine/             # 核心对话引擎
│   ├── hooks/              # 钩子系统
│   ├── mcp/                # MCP 客户端
│   ├── memory/             # 记忆系统
│   ├── permissions/        # 权限系统
│   ├── plugins/            # 插件系统
│   ├── prompts/            # 提示词系统
│   ├── skills/             # 技能系统
│   ├── tasks/              # 任务管理
│   ├── tools/              # 工具集 (31 个基础工具 + 4 个渠道工具)
│   ├── ui/                 # 用户界面
│   │   ├── web/            # Web 后端 (FastAPI + WebSocket)
│   │   └── ...
│   └── cli.py              # CLI 入口
├── frontend/
│   ├── terminal/           # React Ink 终端前端
│   └── web/                # React Web 前端 (Vite + Tailwind)
├── tests/                  # 测试套件
└── pyproject.toml          # 项目配置
```

---

## 🔧 核心模块

### API 客户端层

支持多种 AI 提供商：

| 提供商 | API 格式 | 认证方式 |
|--------|----------|----------|
| Anthropic Claude | anthropic | API Key |
| OpenAI / 兼容接口 | openai | API Key |
| GitHub Copilot | copilot | OAuth 设备码 |
| OpenAI Codex | codex | OAuth 设备码 |
| 自定义格式 | anthropic / openai | API Key |

### 工具系统

提供 31 个基础工具，涵盖：

- **文件操作**: `file_read`, `file_write`, `file_edit`, `notebook_edit`
- **命令执行**: `bash`, `powershell`, `repl`
- **搜索**: `glob`, `grep`, `web_fetch`, `web_search`
- **任务管理**: `task_output`, `task_stop`
- **Agent 协作**: `agent`, `send_message`, `team_create`, `team_delete`
- **模式切换**: `enter_plan_mode`, `exit_plan_mode`
  - `exit_plan_mode` 会触发计划审批：终端/Web 弹出审批卡片，print 模式跨轮次审批（退出码 2），渠道端发送计划内容并等待回复
- **会话控制**: `enter_worktree`, `exit_worktree`, `todo_write`, `sleep`
- **配置与调试**: `config`, `lsp`, `mcp_auth`, `skill`
- **MCP 资源**: `list_mcp_resources`, `read_mcp_resource`
- **交互**: `ask_user_question`
- **定时任务**: `cron`（统一工具，支持 status/list/add/update/remove/run 操作）

### 定时任务与投递链路

定时任务子系统由三个模块协作：

- `services/cron.py` — 任务数据模型（CronJob）与持久化（`cron.json`）
- `services/cron_scheduler.py` — 调度器进程，子进程执行提示词，按 `deliver_to` 字段投递结果到渠道
- `channels/delivery.py` — 渠道投递模块，`parse_deliver_to` 解析目标，`deliver_to_channel` 派发到飞书/微信/QQ 的 `_deliver_*` 函数

投递目标支持 `channel:chat_id` 完全限定格式或仅渠道名（配合 `chat_id` 字段）。任务失败时附 stderr 让用户可见错误。详见 [渠道文档](channels.md#cron-任务结果投递)。

### 权限系统

三种权限模式：

| 模式 | 说明 |
|------|------|
| `default` | 修改类工具需要用户确认 |
| `plan` | 阻止所有修改类工具 |
| `full_auto` | 允许一切操作 |

### 多智能体协调器

内置 7 种专业 Agent：

| Agent | 用途 |
|-------|------|
| `general-purpose` | 通用研究和多步任务 |
| `explore` | 文件搜索和代码探索专家 |
| `plan` | 架构设计和实施规划专家 |
| `verification` | 对抗性验证专家 |
| `worker` | 实现导向的 Worker |
| `statusline-setup` | Shell PS1 转换器 |
| `illusion-guide` | Illusion Agent / SDK / API 文档专家 |

---

## 🎨 前端技术栈

### 终端 TUI（Ink）

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18.3.1 | UI 框架 |
| Ink | 5.1.0 | 终端 UI 组件库 |
| TypeScript | 5.7.3 | 类型安全 |

### Web UI

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18.x | UI 框架 |
| Vite | 6.x | 构建工具和开发服务器 |
| Tailwind CSS | 3.x | 实用优先的 CSS 框架 |
| TypeScript | 5.x | 类型安全 |
| FastAPI | - | 后端 API 框架 |
| WebSocket | - | 实时双向通信 |

---

## 📦 主要依赖

| 依赖 | 用途 |
|------|------|
| anthropic | Anthropic SDK |
| openai | OpenAI SDK |
| rich | 富文本输出 |
| prompt-toolkit | 高级输入处理 |
| typer | CLI 框架 |
| pydantic | 数据验证 |
| httpx | HTTP 客户端 |
| mcp | MCP 协议 |
| fastapi | Web 后端 API 框架 |
| uvicorn | Web 后端 ASGI 服务器 |
