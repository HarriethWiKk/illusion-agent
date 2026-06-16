# IllusionCode

<div align="center">

**AI-Powered Command-Line Programming Assistant**

*The best of many worlds, unified into one intelligent coding tool*

[中文版](README.zh-CN.md) | English

</div>

---

## 📖 Introduction

IllusionCode is an open-source AI-powered command-line programming assistant that brings together the best ideas from many projects and adds its own innovations. It inherits Claude Code's complete prompt system and tool architecture, draws inspiration from OpenHarness's Python architecture design, uses the same Cron task scheduling architecture as OpenClaw, and implements flexible proxy routing through cc-switch. On this foundation, IllusionCode provides deep Windows optimization, full bilingual (Chinese/English) interface support, more comprehensive Markdown terminal rendering than comparable projects, and a browser-based Web UI for a modern chat experience.

### Core Features

- 🌐 **Web UI Interface** - Browser-based chat interface with `illusion web`, featuring warm color design, session management, and real-time streaming (supplementary to the recommended terminal interface)
- 🪟 **Deep Windows Optimization** - Auto-detect Git, PowerShell support, path compatibility optimization
- 🖥️ **Zero Terminal Flicker** - Stable rendering based on Ink Static component, suppressing resize event interference
- 🌍 **Bilingual Interface** - All CLI output automatically switches between Chinese and English based on `ui_language` setting
- 📝 **Comprehensive Markdown Rendering** - Box-drawing tables, rounded card-style code blocks, multi-color rich text, links and more
- 📂 **Project-Level Config Friendly** - Auto-generate skills, rules, mcp, plugins directories, project-level skills override global ones
- 🤖 **Multi AI Provider Support** - Anthropic Claude, OpenAI, GitHub Copilot, OpenAI Codex, and any OpenAI-compatible endpoint
- 🛠️ **Rich Toolset** - 34 built-in tools + MCP dynamic tool extension
- ⌨️ **47 Slash Commands** - Covering session management, configuration, project operations, task scheduling, etc.
- 🧠 **Multi-Agent Collaboration** - 7 built-in specialized Agents, supporting task orchestration
- 🔌 **Flexible Extension System** - Plugins, hooks, skills, MCP servers
- 🔐 **Comprehensive Permission Control** - Three modes + fine-grained rules + Always Allow one-click approval
- 💾 **Memory & Context** - Project knowledge persistence and dynamic retrieval
- 🎨 **Dual Interface** - Modern React + Ink terminal TUI + browser-based Web UI
- 🎯 **Reasoning Effort Control** - Supports low/medium/high/xhigh/max five reasoning effort levels with automatic fallback

### Interface Preview

<div align="center">
  <p>Welcome screen & rich text rendering</p>
  <img src="docs/images/image1.png" alt="IllusionCode welcome screen" width="48%" />
  <img src="docs/images/image2.png" alt="IllusionCode rich text rendering" width="48%" />
</div>

<div align="center">
  <p>Demo video</p>
  <a href="https://www.youtube.com/watch?v=ExrzKVjWPls">
    <img src="docs/images/IllusionCode.png" alt="Click to watch demo video" width="720" />
  </a>
  <p><a href="https://www.youtube.com/watch?v=ExrzKVjWPls">📺 Watch demo on YouTube</a></p>
</div>

### Design Origins & Innovations

**Inherited from Claude Code**: Complete injection of Claude Code's system prompts, tool definitions, permission model, and multi-agent coordination architecture, ensuring behavioral consistency.

**Inspired by OpenHarness**: Python architecture design references OpenHarness's ideas.

**Cron Architecture Aligned with OpenClaw**: The scheduled task system uses the same scheduler architecture as OpenClaw, supporting independent session execution, execution history tracking, and consecutive error monitoring.

**cc-switch Proxy Routing**: Local proxy routing through the cc-switch reverse proxy tool, supporting request forwarding to different AI providers.

**Deep Windows Optimization**: Auto-detect Git installation path, unified PowerShell and Bash tool processing, automatic path separator compatibility, out-of-the-box experience for Windows users.

**Zero Terminal Flicker**: Uses Ink `<Static>` component architecture, static rendering for completed messages, dynamic rendering for streaming messages, completely solving terminal flicker issues.

**Bilingual Interface**: All CLI output (auth, mcp, plugin, cron, session, etc.) automatically switches language via the i18n system based on the `ui_language` field. Language preference can be selected on first run.

**Comprehensive Markdown Rendering**: Full rendering of box-drawing tables, rounded card-style code blocks, multi-color rich text (bold, italic, inline code, links), significantly improving AI response readability.

**Project-Level Config Automation**: Auto-generate `<project>/.illusion/rules/` and `<project>/.illusion/skills/` directories, project-level configuration takes precedence over global configuration, facilitating team collaboration.

**Web UI Interface**: Browser-based chat interface powered by React + Vite + Tailwind CSS frontend and FastAPI + WebSocket backend. Features warm color design, session management, sidebar navigation, real-time streaming responses, right panel with context usage display, and full i18n support. Launch with `illusion web`. Note: The terminal interface is recommended as the primary mode for full feature support and better performance; the Web UI is intended as a supplementary option for scenarios where a terminal is unavailable.

---

## 🚀 Quick Start

### Requirements

- Python >= 3.10
- Node.js 18+
- Supports Windows, macOS, Linux
- Windows users: Auto-detect Git, no manual PATH configuration needed

### Installation

#### Recommended: pip install from PyPI

The simplest way to install IllusionCode. Automatically installs both frontends and registers the `illusion` command globally.

```bash
pip install illusion-code
```

No git clone required — everything is included in the package.

#### Alternative: pip install from source

Clone the repository and install locally. Triggers the hatch build hook to build frontends automatically.

```bash
git clone https://github.com/YunTaiHua/illusion-code.git
cd illusion-code
pip install .
```

Requires Node.js 18+ (for frontend build).

#### Alternative: pip install -e . (editable, from source)

Editable install from source. Like `pip install .`, it triggers the hatch build hook to build frontends automatically and registers `illusion` globally. Like `uv sync`, source code changes take effect immediately without reinstalling.

```bash
git clone https://github.com/YunTaiHua/illusion-code.git
cd illusion-code
pip install -e .
```

Requires Node.js 18+ (for frontend build).

> **When to use**: Best for developers who want both an editable install (live code changes) and the `illusion` command available globally. Unlike `uv sync`, no manual frontend build or `uv run` wrapper is needed.

#### Alternative: uv sync (for development)

`uv sync` creates an editable install within the project directory. It does **not** trigger the hatch build hook, so you must build frontends manually. This is recommended for developers who want to modify the source code.

```bash
git clone https://github.com/your-repo/illusion-code.git
cd illusion-code
uv sync

# Build frontends manually (required after uv sync)
python scripts/build_frontend.py              # Build both
python scripts/build_frontend.py --terminal   # Terminal TUI only
python scripts/build_frontend.py --web        # Web UI only
```

> **Note**: `uv sync` does NOT register `illusion` globally. To use it:
>
> ```bash
> # Option 1: Use uv run from the project directory
> cd illusion-code
> uv run illusion
>
> # Option 2: Activate the virtual environment
> # Windows
> .venv\Scripts\activate
> # macOS / Linux
> source .venv/bin/activate
> illusion
>
> # Option 3: Install globally with pip (recommended)
> pip install .
>
> # Option 4: Editable install with pip (global + live code changes)
> pip install -e .
> ```

#### Manual frontend build (for source installs only)

If you installed from source and need to rebuild frontends (e.g., after updating frontend code). PyPI users do not need this step.

**Build script (recommended)**

```bash
python scripts/build_frontend.py              # Build both
python scripts/build_frontend.py --terminal   # Terminal TUI only
python scripts/build_frontend.py --web        # Web UI only
```

**npm directly**

```bash
# Terminal TUI (esbuild → dist/index.mjs)
cd frontend/terminal
npm install --no-fund --no-audit
npm run build
cd ../..

# Web UI (Vite → dist/)
cd frontend/web
npm install --no-fund --no-audit
npm run build
cd ../..
```

#### Key differences

| | `pip install illusion-code` | `pip install .` | `pip install -e .` | `uv sync` |
|---|---|---|---|---|
| Source | PyPI | Local git clone | Local git clone | Local git clone |
| Frontend build | Pre-built (included) | Automatic (hatch hook) | Automatic (hatch hook) | Manual |
| Node.js required | No | Yes (18+) | Yes (18+) | Yes (18+) |
| `illusion` command | Global | Global | Global | Project-only (via `uv run` or venv activation) |
| Install type | Standard | Standard | Editable | Editable |
| Code changes take effect | Reinstall needed | Reinstall needed | Immediately | Immediately |
| Best for | End users | Contributors | Developers (global + editable) | Developers |

### Basic Usage

> **First-time setup**: Run `illusion auth login` first to configure your API credentials. Without authentication (or if the model is unavailable), the program may exit with an error code.

```bash
# First-time: configure authentication
illusion auth login

# Start interactive session (recommended)
illusion

# Launch Web UI in browser
illusion web

# Web UI with custom port
illusion web --port 8080

# Non-interactive print mode
illusion -p "Analyze the structure of this project"

# Specify model
illusion -m env_1.model_2

# Continue most recent session
illusion --continue

# Restore specific session
illusion --resume <session-id>

# Set permission mode
illusion --permission-mode full_auto

# Specify API format
illusion --api-format openai
```

> **Note**: The terminal interface (`illusion`) is the recommended primary mode. The Web UI (`illusion web`) is a supplementary option for scenarios where a terminal is unavailable.

---

## 📚 Command System

### Subcommands

```bash
# Web UI
illusion web                     # Launch Web UI in browser (default port 3000)
illusion web --port 8080         # Launch with custom port

# Authentication management
illusion auth login              # Interactive provider setup (Custom/Anthropic/OpenAI/Copilot/Codex)
illusion auth status             # View credential status for all environments
illusion auth logout [env_N]     # Clear environment credentials
illusion auth switch [env_N]     # Switch active environment
illusion auth add-model <env_N> <model_name>  # Add a model to an existing environment

# MCP management
illusion mcp list                # List MCP servers
illusion mcp add <name> <config> # Add server
illusion mcp remove <name>       # Remove server

# Plugin management
illusion plugin list             # List plugins
illusion plugin install <source> # Install plugin
illusion plugin uninstall <name> # Uninstall plugin

# Scheduled tasks
illusion cron start              # Start scheduler
illusion cron stop               # Stop scheduler
illusion cron status             # View status
illusion cron list               # List tasks
illusion cron toggle <name> <true|false>  # Enable/disable task
illusion cron run <name>         # Manually trigger task
illusion cron history            # View execution history
illusion cron logs               # View scheduler logs

# Self-update
illusion update                  # Check for and install updates from PyPI
illusion update --deps           # Also update project dependencies
```

### Interactive Slash Commands

In interactive sessions, you can use the following commands:

| Category | Command Examples | Description |
|----------|------------------|-------------|
| Session Management | `/help`, `/clear`, `/exit`, `/rewind`, `/delete` | Manage session state |
| Memory Snapshots | `/memory`, `/resume`, `/export`, `/rules` | Memory and session management |
| Configuration | `/config`, `/model`, `/permissions`, `/plan`, `/thinking` | Adjust runtime configuration |
| Plugin Extensions | `/skills`, `/hooks`, `/mcp`, `/plugin` | Manage extension features |
| Project Git | `/init`, `/diff`, `/branch`, `/commit` | Project and version control |
| Multi-Agent | `/continue` | Agent collaboration |
| Self-Update | `/update` | Check for and install IllusionCode updates |

---

## 🏗️ Project Architecture

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

## 🔧 Core Modules

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

## 🎨 Frontend Tech Stack

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

## 📦 Main Dependencies

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

---

## ⚙️ Configuration Files

### Configuration Overview

| File | Location | Scope | Purpose |
|------|----------|-------|---------|
| `settings.json` | `~/.illusion/settings.json` | Global | Main settings file, API config, permissions, hooks, etc. |
| `credentials.json` | `~/.illusion/credentials.json` | Global | Secure credential storage (API keys, etc.) |
| `CLAUDE.md` | Project root | Project-level | Project instructions and context |
| `MEMORY.md` | Project root | Project-level | Memory entry file |
| `.illusion/mcp/*.json` | Project root | Project-level | MCP server configuration |
| `.illusion/rules/*.md` | Project root | Project-level | Project rule files |
| `.illusion/plugins/*/` | Global or project | Per-plugin | Plugin directories with skills, hooks, MCP |
| `.illusion/skills/*/` | Global or project | Per-skill | Skill directories with SKILL.md |

#### Credentials File (credentials.json)

The credentials file is located at `~/.illusion/credentials.json` for secure API key storage. It is automatically managed by the `illusion auth login` command, but can also be edited manually. Credentials are stored by `env_N` groups, corresponding to the environment configurations in `settings.json`.

```json
{
  "env_1": {
    "api_key": "sk-ant-xxxxx"
  },
  "env_2": {
    "api_key": "sk-xxxxx"
  }
}
```

**Field description:**
- Top-level keys are environment identifiers (env_1, env_2, etc.), matching env_N in settings.json
- Each environment stores credentials like `api_key`
- File permissions are automatically set to 600 (see explanation below)

**API Key Storage Options**: API keys can be stored in two ways, choose based on your needs:

| Method | Location | Advantage | Disadvantage |
|--------|----------|-----------|--------------|
| **Secure mode** | `credentials.json` (managed by `illusion auth login`) | Keys separated from config, easier management, file permissions protected | Requires extra file |
| **Convenient mode** | `env_N.api_key` field in `settings.json` | All config in one file, simple and direct | Keys in plaintext, be careful when sharing config |

Both methods can be mixed. Runtime read priority: `env_N.api_key` > environment variables > `credentials.json`.

> **File Permission 600 Explained**: `600` is a Unix/Linux file permission code meaning "only the file owner can read and write, all other users have no access." In numeric notation: `rw-------`, where `6` (read+write) applies to the owner, `0` to the group, and `0` to others. On Windows systems, this setting is silently skipped (Windows uses a different ACL permission model). This restriction protects API keys from being read by other users on the same system.

### Configuration Priority

Configuration resolution priority (from high to low):

1. **CLI Arguments** - Command-line arguments have the highest priority
2. **Environment Variables** - Such as `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, etc.
3. **Configuration Files** - `~/.illusion/settings.json`
4. **Default Values** - Built-in default configurations

---

### Global Configuration (settings.json)

Global configuration file is located at `~/.illusion/settings.json` and applies to all projects.

#### Configuration Methods

settings.json uses the `env_N` grouped format to manage multiple environment/provider configurations. Each `env_N` is an independent environment configuration (EnvConfig) containing API format, endpoint, API key, and model list. The `model` field references `env_N.model_N` to select the currently active model.

```json
{
  "env_1": {
    "api_format": "anthropic",
    "base_url": null,
    "model_1": "claude-sonnet-4-6",
    "model_2": "claude-opus-4-6"
  },
  "env_2": {
    "api_format": "openai",
    "base_url": "https://api.openai.com/v1",
    "model_1": "gpt-5.4"
  },
  "model": "env_1.model_1",
  "context_window": 200000,
  "system_prompt": null
}
```

> **Tip**: The `model` field format is `env_N.model_N`, used to specify which model of which environment to use. You can switch interactively via the `/model` command. API keys can be placed directly in `env_N.api_key`, or stored in credentials.json via `illusion auth login` (more secure).

#### Complete Configuration Structure

```json
{
  "env_1": {
    "api_format": "anthropic",
    "base_url": null,
    "model_1": "claude-sonnet-4-6",
    "model_2": "claude-opus-4-6"
  },
  "env_2": {
    "api_format": "openai",
    "base_url": "https://api.openai.com/v1",
    "model_1": "gpt-5.4"
  },
  "model": "env_1.model_1",
  "context_window": 200000,
  "system_prompt": null,
  "max_tokens": 16384,
  "max_turns": 200,
  "permission": {
    "mode": "default",
    "allowed_tools": [],
    "denied_tools": [],
    "path_rules": [],
    "denied_commands": []
  },
  "hooks": {},
  "memory": {
    "enabled": true,
    "max_files": 5,
    "max_entrypoint_lines": 200
  },
  "sandbox": {
    "enabled": false,
    "fail_if_unavailable": false,
    "auto_allow_bash_if_sandboxed": true,
    "allow_unsandboxed_commands": true,
    "enabled_platforms": [],
    "excluded_commands": [],
    "network": {
      "allowed_domains": [],
      "denied_domains": [],
      "allow_unix_sockets": [],
      "allow_all_unix_sockets": false,
      "allow_local_binding": false,
      "http_proxy_port": null,
      "socks_proxy_port": null
    },
    "filesystem": {
      "allow_read": [],
      "deny_read": [],
      "allow_write": ["."],
      "deny_write": []
    },
    "ignore_violations": {},
    "enable_weaker_nested_sandbox": false,
    "mandatory_deny_search_depth": 3,
    "allow_git_config": false
  },
  "enabled_plugins": {},
  "mcp_servers": {},
  "ui_language": "en-US",
  "output_style": "default",
  "fast_mode": false,
  "effort": "medium",
  "passes": 1,
  "verbose": false
}
```

#### Configuration Field Description

| Field | Type | Default | Description | Example |
|-------|------|---------|-------------|---------|
| `env_N` | object | - | Environment config group (EnvConfig), supports dynamic env_1, env_2... | See EnvConfig field description below |
| `model` | string | "env_1.model_1" | Active model reference, format: `env_N.model_N` | `"env_2.model_1"` |
| `context_window` | int | 200000 | Context window size | `128000` |
| `system_prompt` | string\|null | null | Custom system prompt (global; can be overridden per env_N) | `"You are a professional Python developer"` |
| `max_tokens` | int | 16384 | Maximum output token count | `32768` |
| `max_turns` | int | 200 | Maximum conversation turns | `500` |
| `ui_language` | string | "en-US" | UI language | `"zh-CN"` |
| `fast_mode` | bool | false | Fast mode | `true` |
| `effort` | string | "medium" | Reasoning effort level: low/medium/high/xhigh/max | `"high"` |
| `passes` | int | 1 | Reasoning pass count (1-8), controls how many times the AI iterates on the same problem; higher values = deeper reasoning but longer time | `2` |
| `verbose` | bool | false | Verbose output mode | `true` |

---

### Environment Configuration (EnvConfig)

IllusionCode supports managing multiple environment/provider configurations through `env_N` groups. Each environment configuration (EnvConfig) corresponds to an independent API provider setup.

#### EnvConfig Field Description

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `api_format` | string | Yes | API format: anthropic / openai |
| `base_url` | string\|null | No | Custom API endpoint, null uses default endpoint |
| `api_key` | string | No | API key (can be filled directly, or left empty for `illusion auth login` to store in credentials.json) |
| `system_prompt` | string\|null | No | System prompt for this environment (overrides global) |
| `model_N` | string | No | Model name, supports multiple: model_1, model_2, model_3... Append `[1m]` for million-token context (e.g. `claude-sonnet-4-6[1m]`) |

#### Multi-Model Configuration Example

Configure multiple models under the same environment, switch via `env_N.model_N`:

```json
{
  "env_1": {
    "api_format": "openai",
    "base_url": "https://integrate.api.nvidia.com/v1",
    "model_1": "stepfun-ai/step-3.5-flash",
    "model_2": "minimaxai/minimax-m2.7",
    "model_3": "meta/llama-3.1-405b-instruct"
  },
  "model": "env_1.model_1"
}
```

> **Million-Token Context**: Anthropic models support the `[1m]` suffix for extended 1M context window. Append it to the model name (e.g. `claude-sonnet-4-6[1m]`). IllusionCode automatically detects this suffix and adjusts the internal context tracking to 1,000,000 tokens.
```

**Ways to switch models**:

```bash
# Method 1: Use /model command to switch interactively
/model

# Method 2: Use -m parameter to specify model
illusion -m env_1.model_2

# Method 3: Modify the model field in settings.json
# Change "model" to "env_1.model_2"
```

---

### Provider Configuration Examples

#### 1. Anthropic Claude API

```json
{
  "env_1": {
    "api_format": "anthropic",
    "base_url": null,
    "model_1": "claude-sonnet-4-6",
    "model_2": "claude-opus-4-6"
  },
  "model": "env_1.model_1"
}
```

> API key can be placed directly in `env_N.api_key`, or stored in credentials.json via `illusion auth login` (more secure).

**Authentication**:
- Interactive setup: `illusion auth login` → select Anthropic
- Environment variable: `ANTHROPIC_API_KEY`

---

#### 2. OpenAI API

```json
{
  "env_1": {
    "api_format": "openai",
    "base_url": "https://api.openai.com/v1",
    "model_1": "gpt-5.4"
  },
  "model": "env_1.model_1"
}
```

> API key can be placed directly in `env_N.api_key`, or stored in credentials.json via `illusion auth login` (more secure).

**Authentication**:
- Interactive setup: `illusion auth login` → select OpenAI
- Environment variable: `OPENAI_API_KEY`

---

#### 3. Custom Provider

After selecting "Custom provider" in `illusion auth login`, enter:

1. API format (openai / anthropic)
2. API endpoint
3. API key
4. Model name

```json
{
  "env_1": {
    "api_format": "openai",
    "base_url": "https://api.your-llm.com/v1",
    "model_1": "your-model-name"
  },
  "model": "env_1.model_1"
}
```

---

#### 4. GitHub Copilot

```bash
# Interactive setup
illusion auth login  # Select GitHub Copilot
```

After completing GitHub authorization in the browser, it configures automatically. Auth data is stored in `~/.illusion/copilot_auth.json`.

```json
{
  "env_1": {
    "api_format": "openai",
    "base_url": "https://api.githubcopilot.com",
    "model_1": "gpt-5.5",
    "provider": "copilot"
  },
  "model": "env_1.model_1"
}
```

**Authentication**: GitHub OAuth device code flow (handled automatically by `illusion auth login`)

**Requirement**: An active GitHub Copilot subscription.

**Supported models**: gpt-5.5, gpt-5.3-codex, claude-opus-4.6, gemini-3.1-pro-preview, etc. (depends on subscription plan)

---

#### 5. OpenAI Codex (ChatGPT Subscription)

```bash
# First install and authenticate Codex CLI
codex auth login

# Then configure in IllusionCode
illusion auth login  # Select OpenAI Codex
```

Codex mode uses ChatGPT subscription authentication, reading credentials from the Codex CLI's auth file (`~/.codex/auth.json`).

```json
{
  "env_1": {
    "api_format": "openai",
    "base_url": "https://chatgpt.com/backend-api",
    "model_1": "codex-mini",
    "provider": "codex"
  },
  "model": "env_1.model_1"
}
```

**Authentication**: External CLI credential binding (requires Codex CLI authentication first)

**Requirement**: [Codex CLI](https://github.com/openai/codex) installed with a ChatGPT Plus/Pro/Team subscription.

---

#### 6. Multi-Provider Mixed Configuration

Configure multiple environments via `illusion auth login`, switch using `illusion auth switch` or `/model`:

```json
{
  "env_1": {
    "api_format": "anthropic",
    "base_url": null,
    "model_1": "claude-sonnet-4-6",
    "model_2": "claude-opus-4-6"
  },
  "env_2": {
    "api_format": "openai",
    "base_url": "https://api.openai.com/v1",
    "model_1": "gpt-5.4"
  },
  "env_3": {
    "api_format": "openai",
    "base_url": "https://api.githubcopilot.com",
    "model_1": "gpt-5.5",
    "provider": "copilot"
  },
  "model": "env_1.model_1"
}
```

> API keys can be placed directly in `env_N.api_key`, or stored in credentials.json (more secure, managed by `illusion auth login`). Copilot/Codex authentication is managed by their respective OAuth flows and does not require manual API key entry.

**Switching methods**:
```bash
# Interactive environment switch
illusion auth switch

# Directly specify environment
illusion auth switch env_2

# Use /model command to switch interactively
/model

# Use -m parameter to specify directly
illusion -m env_2.model_1
```

---

### Project-Level Configuration

Project-level configuration only applies to the current project and is placed in the project root directory.

#### CLAUDE.md - Project Instructions

Create a `CLAUDE.md` file in the project root to provide project-specific context and instructions for AI:

```markdown
# Project Description

This is a Python Web project using the FastAPI framework.

## Code Standards

- Use Python 3.10+ features
- Follow PEP 8 code style
- Use type hints

## Directory Structure

- src/api: API routes
- src/models: Data models
- src/services: Business logic

## Notes

- Do not modify files in the tests/ directory
- Run pytest before committing
```

#### .illusion/rules/ - Rule Files

Create `.md` files in the `.illusion/rules/` directory, each file is an independent rule:

```
Project Root/
├── .illusion/
│   └── rules/
│       ├── python-style.md
│       ├── git-workflow.md
│       └── testing.md
```

#### MCP Server Configuration

MCP servers support three configuration methods, with priority from high to low: **Plugin > Project-level > Global settings**

##### 1. Global Configuration (settings.json)

Configure in the `mcp_servers` field of `~/.illusion/settings.json`, applies to all projects. Both `mcp_servers` (snake_case) and `mcpServers` (camelCase) key names are supported:

```json
{
  "mcp_servers": {
    "solidworks": {
      "type": "stdio",
      "command": "python",
      "args": ["E:\\claudecode\\SolidWorks-MCP\\server.py"],
      "enabled": true
    }
  }
}
```

You can also manage via command line:
```bash
illusion mcp list                # List MCP servers
illusion mcp add <name> <config> # Add server
illusion mcp remove <name>       # Remove server
```

##### 2. Project-level Configuration (.illusion/mcp/)

Create `.json` files in the `.illusion/mcp/` directory under the project root, only applies to the current project (directory auto-generated):

**Method 1: Single Server Configuration (filename as server name)**

```json
// .illusion/mcp/solidworks.json
{
  "type": "stdio",
  "command": "python",
  "args": ["E:\\claudecode\\SolidWorks-MCP\\server.py"],
  "enabled": true
}
```

**Method 2: Multiple Server Configuration (using mcpServers key)**

```json
// .illusion/mcp/servers.json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "./data"],
      "env": {
        "NODE_OPTIONS": "--max-old-space-size=4096"
      }
    },
    "database": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "mcp_server_postgres"],
      "env": {
        "DATABASE_URL": "postgresql://localhost/mydb"
      }
    },
    "remote-api": {
      "type": "http",
      "url": "https://api.example.com/mcp",
      "headers": {
        "Authorization": "Bearer your-token"
      }
    },
    "websocket-service": {
      "type": "ws",
      "url": "wss://ws.example.com/mcp",
      "headers": {}
    }
  }
}
```

##### 3. Plugin Configuration

Place `.mcp.json` or `mcp.json` files in the plugin directory, loaded automatically with the plugin:

```
~/.illusion/plugins/my-plugin/
├── plugin.json      # Plugin manifest
├── .mcp.json        # MCP config (or mcp.json)
└── ...
```

MCP servers from plugins are registered with the format `plugin_name:server_name` to avoid conflicts with other configurations.

##### MCP Server Configuration Types

| Type | Fields | Description |
|------|--------|-------------|
| `stdio` | command, args, env, cwd, log_file, enabled | Communication via standard input/output |
| `http` | url, headers, enabled | Communication via HTTP protocol |
| `ws` | url, headers, enabled | Communication via WebSocket protocol |

> **`enabled` field**: All MCP server types support the `enabled` field (defaults to `true`). Set to `false` to disable a single server without removing its configuration. Both `mcpServers` and `mcp_servers` key names are supported in project-level config files.

---

### Permission Configuration

#### Permission Modes

| Mode | Value | Description |
|------|-------|-------------|
| Default Mode | `default` | Modification tools require user confirmation |
| Plan Mode | `plan` | Block all modification tools |
| Full Auto Mode | `full_auto` | Allow all operations |

#### Permission Configuration Example

```json
{
  "permission": {
    "mode": "default",
    "allowed_tools": ["read_file", "grep", "glob"],
    "denied_tools": ["bash"],
    "path_rules": [
      {"pattern": "src/**", "allow": true},
      {"pattern": "secrets/**", "allow": false}
    ],
    "denied_commands": ["/init", "/commit"]
  }
}
```

---

### Hook Configuration

Hooks allow executing custom operations when specific events occur. The hook system is fully aligned with Claude Code.

#### Supported Hook Events (27 events)

| Event | Matcher Field | Description |
|-------|---------------|-------------|
| `PreToolUse` | tool_name | Before tool execution |
| `PostToolUse` | tool_name | After tool execution |
| `PostToolUseFailure` | tool_name | After tool execution fails |
| `PermissionDenied` | tool_name | After auto mode classifier denies |
| `Notification` | notification_type | When notifications are sent |
| `UserPromptSubmit` | — | When user submits a prompt |
| `SessionStart` | source | New session started (startup/resume/clear/compact) |
| `SessionEnd` | reason | Session ending |
| `Stop` | — | Before Claude concludes response |
| `StopFailure` | error | Turn ends due to API error |
| `SubagentStart` | agent_type | Subagent started |
| `SubagentStop` | agent_type | Subagent concludes |
| `PreCompact` | trigger | Before compaction (manual/auto) |
| `PostCompact` | trigger | After compaction |
| `PermissionRequest` | tool_name | Permission dialog displayed |
| `Setup` | trigger | Repo setup (init/maintenance) |
| `ConfigChange` | source | Configuration file changes |
| `InstructionsLoaded` | load_reason | Instruction file loaded |
| `WorktreeCreate` | — | Create worktree |
| `WorktreeRemove` | — | Remove worktree |
| `CwdChanged` | — | Working directory changes |
| `FileChanged` | — | Watched file changes |
| `TaskCreated` | — | Task being created |
| `TaskCompleted` | — | Task being completed |
| `TeammateIdle` | — | Teammate about to idle |
| `Elicitation` | mcp_server_name | MCP elicitation request |
| `ElicitationResult` | mcp_server_name | After user responds to elicitation |

#### Hook Configuration Format

Hooks use a matcher-based structure (aligned with Claude Code):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "echo 'Tool: $ARGUMENTS' >> /tmp/tool.log",
            "timeout": 30
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "http",
            "url": "https://hooks.example.com/tool-complete",
            "headers": {"Authorization": "Bearer token"}
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Check if user input contains sensitive information"
          }
        ]
      }
    ]
  }
}
```

#### Matcher Patterns

The `matcher` field filters when hooks run:

| Pattern | Example | Behavior |
|---------|---------|----------|
| Empty / `*` | `""` | Matches everything |
| Exact match | `"Bash"` | Matches exact tool name |
| Pipe-separated | `"Write\|Edit"` | Matches any in list |
| Regex | `"^git .*"` | Regex match against tool name |

#### Hook Types

| Type | Required | Optional | Description |
|------|----------|----------|-------------|
| `command` | `command` | `if`, `shell`, `timeout`, `statusMessage`, `once`, `async`, `asyncRewake` | Execute Shell command |
| `prompt` | `prompt` | `if`, `model`, `timeout`, `statusMessage`, `once` | Use LLM for verification |
| `http` | `url` | `if`, `timeout`, `headers`, `allowedEnvVars`, `statusMessage`, `once` | Send HTTP POST request |
| `agent` | `prompt` | `if`, `model`, `timeout`, `statusMessage`, `once` | Use Agent for verification |

#### Common Hook Options

| Option | Type | Description |
|--------|------|-------------|
| `if` | string | Permission rule syntax filter (e.g. `"Bash(git *)"`) |
| `timeout` | int | Timeout in seconds |
| `once` | bool | If true, hook runs once then auto-removes |
| `statusMessage` | string | Custom spinner message while hook runs |

#### Command Hook Environment Variables

Command hooks receive these environment variables:

| Variable | Description |
|----------|-------------|
| `CLAUDE_PROJECT_DIR` | Current working directory |
| `CLAUDE_SESSION_ID` | Current session ID |
| `CLAUDE_PLUGIN_ROOT` | Plugin installation directory (if from plugin) |
| `CLAUDE_PLUGIN_DATA` | Plugin data directory |
| `CLAUDE_ENV_FILE` | Write bash exports here to apply env to subsequent commands |

Use `$ARGUMENTS` in the command string to inject the hook input JSON.

---

### Environment Variables

Supported environment variables:

| Variable Name | Description |
|---------------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_MODEL` | Default model |
| `ANTHROPIC_BASE_URL` | API endpoint |
| `ILLUSION_MAX_TOKENS` | Maximum token count |
| `ILLUSION_MAX_TURNS` | Maximum conversation turns |
| `ILLUSION_SANDBOX_ENABLED` | Whether to enable sandbox |
| `ILLUSION_CONFIG_DIR` | Configuration directory path |
| `ILLUSION_DATA_DIR` | Data directory path |
| `ILLUSION_LOGS_DIR` | Logs directory path |

---

### Memory System Configuration

```json
{
  "memory": {
    "enabled": true,
    "max_files": 5,
    "max_entrypoint_lines": 200
  }
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | true | Whether to enable memory function |
| `max_files` | 5 | Maximum number of memory files |
| `max_entrypoint_lines` | 200 | Maximum lines for entry file |

---

### Sandbox Configuration

The sandbox system provides OS-level isolation for shell commands, restricting filesystem and network access. Built with a Python-native runtime, it supports three platforms:

| Platform | Isolation Mechanism | Dependencies |
|----------|-------------------|--------------|
| Linux / WSL | bubblewrap (bwrap) + optional seccomp | `bwrap`, `socat` (for network isolation) |
| macOS | Apple Seatbelt (sandbox-exec) | Built-in |
| Windows | Job Objects + Restricted Tokens + Low Integrity | `pywin32` |

#### Basic Configuration

```json
{
  "sandbox": {
    "enabled": true,
    "fail_if_unavailable": false,
    "auto_allow_bash_if_sandboxed": true,
    "allow_unsandboxed_commands": true,
    "enabled_platforms": [],
    "excluded_commands": []
  }
}
```

#### Main Settings Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `bool` | `false` | Enable sandbox. When enabled, shell commands run in an isolated environment with filesystem and network access constrained by `filesystem` and `network` settings |
| `fail_if_unavailable` | `bool` | `false` | Exit with error if sandbox cannot start. When `true`, the program exits if dependencies like `bwrap`/`sandbox-exec`/`pywin32` are missing, instead of running without sandbox |
| `auto_allow_bash_if_sandboxed` | `bool` | `true` | Auto-allow bash commands when sandboxed. When `false`, each bash command requires manual user confirmation |
| `allow_unsandboxed_commands` | `bool` | `true` | Allow LLM to use `dangerouslyDisableSandbox: true` to bypass sandbox. When `false`, the LLM cannot bypass sandbox restrictions |
| `enabled_platforms` | `list[str]` | `[]` | Restrict sandbox to specific platforms (empty list = all platforms). Options: `linux`, `macos`, `windows`, `wsl`. Example: `["linux", "wsl"]` enables sandbox only on Linux and WSL |
| `excluded_commands` | `list[str]` | `[]` | Command patterns to exclude from sandboxing. Matched commands skip sandbox wrapping and execute directly (see excluded commands section below) |
| `ignore_violations` | `dict` | `{}` | Violation ignore rules. Format: `{"command_pattern": ["path1", "path2"]}`. Matching violations are not recorded or reported |
| `enable_weaker_nested_sandbox` | `bool` | `false` | Set to `true` when running inside Docker containers to skip `--proc /proc` mount and avoid nested sandbox conflicts |
| `mandatory_deny_search_depth` | `int` | `3` | Max directory depth for searching dangerous files (e.g., `.bashrc`, `.gitconfig`) in project subdirectories. Range 1-10, only effective when `deny_write`/`deny_read` are configured |
| `allow_git_config` | `bool` | `false` | Allow writes to `.git/config` files. By default, `.git/config` is protected to prevent malicious git configuration changes |

#### Network Configuration

```json
{
  "sandbox": {
    "network": {
      "allowed_domains": ["api.anthropic.com", "*.github.com"],
      "denied_domains": ["malicious.example.com"],
      "allow_unix_sockets": [],
      "allow_all_unix_sockets": false,
      "allow_local_binding": false,
      "http_proxy_port": null,
      "socks_proxy_port": null
    }
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `allowed_domains` | `list[str]` | `[]` | Allowed domains for network access (supports `*.example.com` wildcards). Unmatched domains trigger a confirmation prompt. On Linux, enforced via HTTP/SOCKS5 proxy + `--unshare-net`; on macOS via Seatbelt `allow network*` |
| `denied_domains` | `list[str]` | `[]` | Denied domains for network access. Matched domains are blocked immediately without confirmation. Takes priority over `allowed_domains` |
| `allow_unix_sockets` | `list[str]` | `[]` | macOS only: list of allowed Unix socket paths. Used to allow specific inter-process communication |
| `allow_all_unix_sockets` | `bool` | `false` | Allow all Unix socket connections. Setting to `true` disables seccomp AF_UNIX blocking on Linux, allowing processes inside the sandbox to create Unix sockets freely |
| `allow_local_binding` | `bool` | `false` | Allow processes inside the sandbox to bind to local ports. By default, sandbox blocks all port binding to prevent port conflicts and security risks |
| `http_proxy_port` | `int?` | `null` | Use an external HTTP proxy port instead of starting a local proxy. Useful in environments with existing proxy infrastructure |
| `socks_proxy_port` | `int?` | `null` | Use an external SOCKS5 proxy port instead of starting a local proxy |

> **Domain validation rules**:
> - Rejects overly broad patterns like `*` or `*.com`
> - `*.example.com` requires at least 2 dot-separated parts after `*.`
> - Rejects patterns containing `://`, `/`, or `:`
> - `localhost` is always allowed

#### Filesystem Configuration

```json
{
  "sandbox": {
    "filesystem": {
      "allow_write": [".", "./output"],
      "deny_write": [".git/hooks", ".env"],
      "deny_read": ["./secrets"],
      "allow_read": ["./secrets/public"]
    }
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `allow_write` | `list[str]` | `["."]` | Paths allowed for writing. On Linux/macOS, enforced at OS level via bwrap `--bind`/Seatbelt `allow file-write*`; on Windows, only checked at application layer |
| `deny_write` | `list[str]` | `[]` | Paths denied for writing, takes priority over `allow_write`. Shows three-option confirmation dialog on match. On Linux, blocked via `--ro-bind /dev/null` mount; on macOS, blocked via Seatbelt `deny file-write*` |
| `deny_read` | `list[str]` | `[]` | Paths denied for reading. Shows three-option confirmation dialog (Allow / Allow for session / Deny) on match. Affects `read_file`, `grep`, `glob`, `lsp` and other tools |
| `allow_read` | `list[str]` | `[]` | Paths re-allowed for reading within denied regions. Example: `deny_read: ["~/.ssh"]` + `allow_read: ["~/.ssh/known_hosts"]` allows reading the known_hosts file |

#### Excluded Commands

`excluded_commands` supports three matching patterns:

```json
{
  "sandbox": {
    "excluded_commands": [
      "npm test",
      "make:*",
      "git status"
    ]
  }
}
```

| Pattern | Example | Matches |
|---------|---------|---------|
| Exact match | `"npm test"` | `npm test` |
| Wildcard | `"make:*"` | `make:build`, `make:clean` |
| Prefix match | `"git push"` | `git push origin main` |

The system automatically splits compound commands (`&&`, `||`, `;`, `|`) and strips environment variable prefixes (`FOO=bar cmd` → `cmd`) and safe wrappers (`sudo`, `env`, `time`) to prevent bypass via `safe_cmd && evil_cmd`.

#### Sandbox Blocking Behavior

When an LLM operation triggers a sandbox restriction (e.g., reading a file in `deny_read`), the system shows a three-option confirmation dialog:

```
┌─────────────────────────────────────────────┐
│ Allow access to 'E:\PyCode\API.txt'?       │
│                                             │
│  1. Allow              (single operation)   │
│  2. Allow for session  (resets on restart)  │
│  3. Deny               (block operation)    │
└─────────────────────────────────────────────┘
```

| Option | Effect | Persistence |
|--------|--------|-------------|
| Allow | Allow this single operation | One-time only |
| Allow for session | Allow this path for the current session | Resets on restart |
| Deny | Block the operation, return error to LLM | None |

> **Difference from `permission.denied_tools`**:
> - `sandbox.filesystem.deny_read` → Shows three-option confirmation dialog, user can choose to allow
> - `permission.denied_tools` → Hard deny, terminates operation immediately with no confirmation

#### Filesystem Restriction Effects

| Field | Affected Tools | Enforcement Level |
|-------|---------------|-------------------|
| `deny_read` | `read_file`, `grep`, `glob`, `lsp` | Permission checker (application layer) |
| `deny_write` | `edit`, `write`, `bash` (write ops) | Permission checker + OS-level sandbox |
| `allow_write` | `bash` (write ops) | OS-level sandbox (bwrap/Seatbelt) |

- **Linux/macOS**: `deny_write` is enforced at both application layer and OS level (bwrap `--ro-bind`, Seatbelt `deny file-write*`)
- **Windows**: Only enforced at application layer (Job Objects don't provide filesystem isolation)

#### Full Example

```json
{
  "sandbox": {
    "enabled": true,
    "fail_if_unavailable": true,
    "auto_allow_bash_if_sandboxed": true,
    "allow_unsandboxed_commands": true,
    "excluded_commands": ["git status", "git log", "git diff"],
    "network": {
      "allowed_domains": ["*.github.com", "*.npmjs.org", "pypi.org", "*.pypi.org"]
    },
    "filesystem": {
      "allow_write": ["."],
      "deny_write": [".git/hooks", ".env", ".env.*"],
      "deny_read": ["~/.ssh", "~/.gnupg"]
    }
  }
}
```

#### Environment Variable Overrides

| Environment Variable | Overrides |
|---------------------|-----------|
| `ILLUSION_SANDBOX_ENABLED` | `sandbox.enabled` (`1`/`true`/`yes`/`on` = true) |
| `ILLUSION_SANDBOX_FAIL_IF_UNAVAILABLE` | `sandbox.fail_if_unavailable` |

#### /sandbox Command

| Command | Description |
|---------|-------------|
| `/sandbox` or `/sandbox status` | Show current sandbox status |
| `/sandbox exclude <pattern>` | Add an excluded command pattern |

---

## 🔌 Extension Development

### Plugin System

Plugins extend IllusionCode with skills, hooks, commands, and MCP servers. Plugin format is fully aligned with Claude Code.

#### Plugin Directory Structure

```
my-plugin/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest
├── skills/                  # Skills (subdirs with SKILL.md)
│   ├── my-skill/
│   │   └── SKILL.md
│   └── another-skill.md
├── commands/                # Slash commands (.md files)
├── agents/                  # Agent definitions (.md files)
├── hooks/
│   └── hooks.json           # Hook definitions
├── .mcp.json                # MCP server configuration
└── settings.json            # Plugin default settings
```

#### Plugin Manifest (plugin.json)

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "My custom plugin",
  "enabled_by_default": true,
  "skills_dir": "skills",
  "hooks_file": "hooks.json"
}
```

#### Plugin Installation

```bash
# Install from local path
illusion plugin install /path/to/my-plugin

# List installed plugins
illusion plugin list

# Enable/disable
illusion plugin enable my-plugin
illusion plugin disable my-plugin

# Uninstall
illusion plugin uninstall my-plugin
```

Plugins are installed to `~/.illusion/plugins/` (user-level) or `.illusion/plugins/` (project-level).

#### Plugin Hooks (hooks/hooks.json)

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/init.cmd\""
          }
        ]
      }
    ]
  }
}
```

Plugin hooks support `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_DATA}` variable substitution.

#### Skill Frontmatter

Skills defined in SKILL.md files support these frontmatter fields:

```yaml
---
description: What this skill does
allowed-tools: Bash, Read, Write
model: claude-sonnet-4-6
context: fork
effort: high
hooks:
  PreToolUse:
    - matcher: Bash
      hooks:
        - type: command
          command: echo check
---
```

| Field | Type | Description |
|-------|------|-------------|
| `description` | string | Skill description (shown in skill list) |
| `allowed-tools` | string | Comma-separated list of allowed tools |
| `model` | string | Model override for this skill |
| `context` | string | `inline` (expand into conversation) or `fork` (sub-agent) |
| `effort` | string | Reasoning effort override |
| `hooks` | object | Hooks to register when skill is invoked |

### Hook System

See [Hook Configuration](#hook-configuration) for the full hook documentation with 27 events and matcher-based format.

## 🧪 Development & Testing

```bash
# Install development dependencies
uv sync --dev

# Run tests
pytest
```

---

## 📄 License

This project is open-sourced under the [MIT](LICENSE) license.

---

## 🤝 Contributing

Welcome to submit Issues and Pull Requests!

---

</div>