# Project Architecture

```
illusion-code/
├── src/illusion/           # Main source code
│   ├── api/                # API clients (Anthropic, OpenAI, etc.)
│   ├── auth/               # Authentication management
│   ├── commands/           # Slash command system (47 commands)
│   ├── config/             # Configuration system
│   ├── coordinator/        # Multi-agent coordinator
│   ├── engine/             # Core conversation engine
│   ├── hooks/              # Hook system
│   ├── mcp/                # MCP client
│   ├── memory/             # Memory system
│   ├── permissions/        # Permission system
│   ├── plugins/            # Plugin system
│   ├── prompts/            # Prompt system
│   ├── skills/             # Skill system
│   ├── tasks/              # Task management
│   ├── tools/              # Toolset (34 base tools)
│   ├── ui/                 # User interface
│   │   ├── web/            # Web backend (FastAPI + WebSocket)
│   │   └── ...
│   └── cli.py              # CLI entry point
├── frontend/
│   ├── terminal/           # React Ink TUI frontend
│   └── web/                # React Web frontend (Vite + Tailwind)
├── tests/                  # Test suite
└── pyproject.toml          # Project configuration
```

---

## Core Modules

### API Client Layer

Supports multiple AI providers:

| Provider | API Format | Authentication |
|----------|------------|----------------|
| Anthropic Claude | anthropic | API Key |
| OpenAI / Compatible | openai | API Key |
| GitHub Copilot | openai | OAuth Device Flow |
| OpenAI Codex | openai | External CLI (Codex CLI) |
| Custom Provider | anthropic / openai | API Key |

### Tool System

Provides 34 core tools, covering:

- **File Operations**: `file_read`, `file_write`, `file_edit`, `notebook_edit`
- **Command Execution**: `bash`, `powershell`, `repl`
- **Search**: `glob`, `grep`, `web_fetch`, `web_search`, `tool_search`
- **Task Management**: `task_create`, `task_get`, `task_list`, `task_update`, `task_output`, `task_stop`
- **Agent Collaboration**: `agent`, `send_message`, `team_create`, `team_delete`
- **Mode Switching**: `enter_plan_mode`, `exit_plan_mode`
- **Session Control**: `enter_worktree`, `exit_worktree`, `todo_write`, `sleep`
- **Config & Debug**: `config`, `lsp`, `mcp_auth`, `skill`, `structured_output`
- **Interaction**: `ask_user_question`
- **Scheduled Tasks**: `cron` (unified tool with status/list/add/update/remove/run actions)

### Permission System

Three permission modes:

| Mode | Description |
|------|-------------|
| `default` | Modification tools require user confirmation |
| `plan` | Block all modification tools |
| `full_auto` | Allow all operations |

### Multi-Agent Coordinator

Built-in 7 specialized Agents:

| Agent | Purpose |
|-------|---------|
| `general-purpose` | General research and multi-step tasks |
| `Explore` | File search and code exploration expert |
| `Plan` | Architecture design and implementation planning expert |
| `verification` | Adversarial verification expert |
| `worker` | Implementation-oriented Worker |
| `statusline-setup` | Shell PS1 converter |
| `illusion-guide` | Illusion Code / SDK / API documentation expert |

---

## Frontend Tech Stack

### Terminal TUI (Ink)

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.3.1 | UI framework |
| Ink | 5.1.0 | Terminal UI component library |
| TypeScript | 5.7.3 | Type safety |

### Web UI

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.x | UI framework |
| Vite | 6.x | Build tool and dev server |
| Tailwind CSS | 3.x | Utility-first CSS framework |
| TypeScript | 5.x | Type safety |
| FastAPI | - | Backend API framework |
| WebSocket | - | Real-time bidirectional communication |

---

## Main Dependencies

| Dependency | Purpose |
|------------|---------|
| anthropic | Anthropic SDK |
| openai | OpenAI SDK |
| rich | Rich text output |
| prompt-toolkit | Advanced input processing |
| textual | TUI framework |
| typer | CLI framework |
| pydantic | Data validation |
| httpx | HTTP client |
| mcp | MCP protocol |
| fastapi | Web backend API framework |
| uvicorn | ASGI server for Web backend |
