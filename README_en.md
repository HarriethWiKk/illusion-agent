# IllusionCode

<div align="center">

**AI-Powered Command-Line Programming Assistant**

*Python port of Claude Code | Adapted from OpenHarness (0.1.0)*

[中文版](README.md) | English

</div>

---

## 📖 Introduction

IllusionCode is an open-source AI-powered command-line programming assistant, migrated and adapted from OpenHarness (0.1.0) with full Claude Code prompt injection and optimized details and configurations. It helps developers efficiently complete software engineering tasks. It supports multiple AI providers, offers a rich set of tools and command systems, and features multi-agent collaboration capabilities.

### Core Features

- 🪟 **Deep Windows Optimization** - Auto-detect Git, PowerShell support, path compatibility optimization
- 🖥️ **Zero Terminal Flicker** - Stable rendering based on Ink Static component, suppressing resize event interference
- 🌍 **Full Chinese Support** - Command system, UI selectors, error messages fully localized for better Chinese user experience
- 📝 **Markdown Terminal Rendering** - Supports tables, bold, italic, inline code, links and other rich text styles
- 📂 **Project-Level Config Friendly** - Auto-generate skills 、 rules 、 mcp 、 plunges directories, project-level skills override global ones
- 🤖 **Multi AI Provider Support** - Anthropic Claude, OpenAI, GitHub Copilot, Alibaba Cloud DashScope, etc.
- 🛠️ **Rich Toolset** - 38+ built-in tools + MCP dynamic tool extension
- ⌨️ **51 Slash Commands** - Covering session management, configuration, project operations, task scheduling, etc.
- 🧠 **Multi-Agent Collaboration** - 7 built-in specialized Agents, supporting task orchestration
- 🔌 **Flexible Extension System** - Plugins, hooks, skills, MCP servers
- 🔐 **Comprehensive Permission Control** - Three modes + fine-grained rules + Always Allow one-click approval
- 💾 **Memory & Context** - Project knowledge persistence and dynamic retrieval
- 🎨 **Modern Terminal Interface** - React + Ink component-based TUI

### Project Highlights

**Windows User Friendly**: Auto-detect Git installation path, unified PowerShell and Bash tool processing, automatic path separator compatibility, out-of-the-box experience for Windows users.

**Zero Terminal Flicker**: Uses Ink `<Static>` component architecture, static rendering for completed messages, dynamic rendering for streaming messages, completely solving terminal flicker issues.

**Chinese Experience First**: All 51 slash commands support Chinese responses, UI selectors fully localized, multi-line messages translated line by line, error messages bilingual.

**Markdown Rich Text Rendering**: Full rendering of tables, bold, italic, inline code, links and other formats in terminal, significantly improving AI response readability.

**Project-Level Config Automation**: Auto-detect `<project>/.claude/rules/` and `<project>/.claude/skills/` directories, project-level configuration takes precedence over global configuration, facilitating team collaboration.

---

## 🚀 Quick Start

### Requirements

- Python >= 3.10
- Node.js (for frontend TUI)
- Supports Windows, macOS, Linux
- Windows users: Auto-detect Git, no manual PATH configuration needed

### Installation

```bash
git clone https://github.com/your-repo/illusion-code.git
cd illusion-code
uv sync
```

### Basic Usage

```bash
# Start interactive session (recommended)
illusion

# Non-interactive print mode
illusion -p "Analyze the structure of this project"

# Specify model
illusion -m sonnet

# Continue most recent session
illusion --continue

# Restore specific session
illusion --resume <session-id>

# Set permission mode
illusion --permission-mode full_auto

# Specify API provider
illusion --api-format copilot
```

---

## 📚 Command System

### Subcommands

```bash
# Authentication management
illusion auth login              # Login
illusion auth status             # View authentication status
illusion auth logout             # Logout
illusion auth switch <provider>  # Switch provider

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
```

### Interactive Slash Commands

In interactive sessions, you can use the following commands:

| Category | Command Examples | Description |
|----------|------------------|-------------|
| Session Management | `/help`, `/clear`, `/exit`, `/rewind`, `/delete` | Manage session state |
| Memory Snapshots | `/memory`, `/resume`, `/export`, `/rules` | Memory and session management |
| Configuration | `/config`, `/model`, `/permissions`, `/plan` | Adjust runtime configuration |
| Plugin Extensions | `/skills`, `/hooks`, `/mcp`, `/plugin` | Manage extension features |
| Project Git | `/init`, `/diff`, `/branch`, `/commit` | Project and version control |
| Multi-Agent | `/agents`, `/tasks`, `/continue` | Agent collaboration |

---

## 🏗️ Project Architecture

```
illusion-code/
├── src/illusion/           # Main source code
│   ├── api/                # API clients (Anthropic, OpenAI, Copilot, etc.)
│   ├── auth/               # Authentication management
│   ├── commands/           # Slash command system (51 commands)
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
│   ├── tools/              # Toolset (38+ tools)
│   ├── ui/                 # User interface
│   └── cli.py              # CLI entry point
├── frontend/terminal/      # React TUI frontend
├── tests/                  # Test suite
└── pyproject.toml          # Project configuration
```

---

## 🔧 Core Modules

### API Client Layer

Supports multiple AI providers:

| Provider | API Format | Authentication |
|----------|------------|----------------|
| Anthropic Claude | anthropic | API Key / OAuth |
| OpenAI | openai | API Key |
| GitHub Copilot | copilot | OAuth Device Flow |
| Alibaba Cloud DashScope | openai | API Key |
| AWS Bedrock | anthropic | API Key |
| Google Vertex | anthropic | API Key |

### Tool System

Provides 38+ core tools, covering:

- **File I/O**: `bash`, `read_file`, `write_file`, `edit_file`
- **Search**: `glob`, `grep`, `web_fetch`, `web_search`
- **Task Management**: `task_create`, `task_list`, `task_stop`
- **Scheduled Tasks**: `cron` (unified tool with status/list/add/update/remove/run actions)
- **Multi-Agent**: `agent`, `send_message`, `team_create`
- **Mode Switching**: `enter_plan_mode`, `exit_plan_mode`

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
| `Explore` | Read-only file search expert |
| `Plan` | Read-only architecture/planning expert |
| `verification` | Adversarial verification expert |
| `worker` | Implementation-oriented Worker |
| `statusline-setup` | Shell PS1 converter |
| `claude-code-guide` | Documentation expert |

---

## 🎨 Frontend Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.3.1 | UI framework |
| Ink | 5.1.0 | Terminal UI component library |
| TypeScript | 5.7.3 | Type safety |

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

#### Credentials File (credentials.json)

The credentials file is located at `~/.illusion/credentials.json` for secure API key storage. It is automatically managed by the `illusion auth login` command, but can also be edited manually.

```json
{
  "anthropic": {
    "api_key": "sk-ant-xxxxx"
  },
  "openai": {
    "api_key": "sk-xxxxx"
  },
  "dashscope": {
    "api_key": "sk-xxxxx"
  }
}
```

**Field description:**
- Top-level keys are provider identifiers (anthropic, openai, dashscope, etc.)
- Each provider can store credentials like `api_key`
- File permissions are automatically set to 600 (owner read/write only)

### Configuration Priority

Configuration resolution priority (from high to low):

1. **CLI Arguments** - Command-line arguments have the highest priority
2. **Environment Variables** - Such as `ANTHROPIC_API_KEY`, `illusion_MODEL`, etc.
3. **Configuration Files** - `~/.illusion/settings.json`
4. **Default Values** - Built-in default configurations

---

### Global Configuration (settings.json)

Global configuration file is located at `~/.illusion/settings.json` and applies to all projects.

#### Configuration Methods

settings.json uses the `env_N` grouped format to manage multiple environment/provider configurations. Each `env_N` is an independent environment configuration (EnvConfig) containing API format, endpoint, API key, and model list. The `model` field references `env_N:model_N` to select the currently active model.

```json
{
  "env_1": {
    "api_format": "anthropic",
    "base_url": null,
    "model_1": "claude-sonnet-4-6",
    "model_2": "claude-opus-4-6",
    "api_key": "sk-ant-xxxxx"
  },
  "env_2": {
    "api_format": "copilot",
    "base_url": "https://api.githubcopilot.com",
    "model_1": "gpt-5.5",
    "model_2": "gemini-3.1-pro",
    "model_3": "grok-4-fast"
  },
  "model": "env_1:model_1",
  "context_window": 200000,
  "system_prompt": null
}
```

> **Tip**: The `model` field format is `env_N:model_N`, used to specify which model of which environment to use. You can switch interactively via the `/model` command.

#### Complete Configuration Structure

```json
{
  "env_1": {
    "api_format": "anthropic",
    "base_url": null,
    "model_1": "claude-sonnet-4-6",
    "model_2": "claude-opus-4-6",
    "api_key": "sk-ant-xxxxx"
  },
  "env_2": {
    "api_format": "openai",
    "base_url": "https://api.openai.com/v1",
    "model_1": "gpt-5.4",
    "api_key": "sk-xxxxx"
  },
  "model": "env_1:model_1",
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
    "enabled_platforms": [],
    "network": {
      "allowed_domains": [],
      "denied_domains": []
    },
    "filesystem": {
      "allow_read": [],
      "deny_read": [],
      "allow_write": ["."],
      "deny_write": []
    }
  },
  "enabled_plugins": {},
  "mcp_servers": {},
  "ui_language": "en",
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
| `model` | string | "env_1:model_1" | Active model reference, format: `env_N:model_N` | `"env_2:model_1"` |
| `context_window` | int | 200000 | Context window size | `128000` |
| `system_prompt` | string\|null | null | Custom system prompt (global override) | `"You are a professional Python developer"` |
| `max_tokens` | int | 16384 | Maximum output token count | `32768` |
| `max_turns` | int | 200 | Maximum conversation turns | `500` |
| `ui_language` | string | "en" | UI language | `"zh-CN"` |
| `fast_mode` | bool | false | Fast mode | `true` |
| `effort` | string | "medium" | Effort level: low/medium/high | `"high"` |
| `verbose` | bool | false | Verbose output mode | `true` |

---

### Environment Configuration (EnvConfig)

IllusionCode supports managing multiple environment/provider configurations through `env_N` groups. Each environment configuration (EnvConfig) corresponds to an independent API provider setup.

#### EnvConfig Field Description

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `api_format` | string | Yes | API format: anthropic / openai / copilot |
| `base_url` | string\|null | No | Custom API endpoint, null uses default endpoint |
| `api_key` | string | No | API key (recommend using environment variables or credential storage) |
| `system_prompt` | string\|null | No | System prompt for this environment (overrides global) |
| `model_N` | string | No | Model name, supports multiple: model_1, model_2, model_3... |

#### Multi-Model Configuration Example

Configure multiple models under the same environment, switch via `env_N:model_N`:

```json
{
  "env_1": {
    "api_format": "openai",
    "base_url": "https://integrate.api.nvidia.com/v1",
    "model_1": "stepfun-ai/step-3.5-flash",
    "model_2": "minimaxai/minimax-m2.7",
    "model_3": "meta/llama-3.1-405b-instruct",
    "api_key": "nvapi-xxxxx"
  },
  "model": "env_1:model_1"
}
```

**Ways to switch models**:

```bash
# Method 1: Use /model command to switch interactively
/model

# Method 2: Use -m parameter to specify model
illusion -m env_1:model_2

# Method 3: Modify the model field in settings.json
# Change "model" to "env_1:model_2"
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
    "model_2": "claude-opus-4-6",
    "api_key": "sk-ant-xxxxx"
  },
  "model": "env_1:model_1"
}
```

**Authentication**:
- Environment variable: `ANTHROPIC_API_KEY`
- Credential storage: `illusion auth login anthropic`

**Supported Model Aliases**:
| Alias | Actual Model | Description |
|-------|--------------|-------------|
| `default` | claude-sonnet-4-6 | Recommended model |
| `best` | claude-opus-4-6 | Most powerful model |
| `sonnet` | claude-sonnet-4-6 | Daily coding |
| `opus` | claude-opus-4-6 | Complex reasoning |
| `haiku` | claude-haiku-4-5 | Fastest model |
| `sonnet[1m]` | claude-sonnet-4-6[1m] | 1M context |
| `opus[1m]` | claude-opus-4-6[1m] | 1M context |
| `opusplan` | Dynamic selection | Plan mode uses Opus |

---

#### 2. Claude Subscription

```json
{
  "env_1": {
    "api_format": "anthropic",
    "base_url": null,
    "model_1": "claude-sonnet-4-6",
    "model_2": "claude-opus-4-6"
  },
  "model": "env_1:model_1"
}
```

**Authentication**:
```bash
illusion auth claude-login
```

---

#### 3. OpenAI API

```json
{
  "env_1": {
    "api_format": "openai",
    "base_url": "https://api.openai.com/v1",
    "model_1": "gpt-5.4",
    "api_key": "sk-xxxxx"
  },
  "model": "env_1:model_1"
}
```

**Authentication**:
- Environment variable: `OPENAI_API_KEY`
- Credential storage: `illusion auth login openai`

---

#### 4. GitHub Copilot

```json
{
  "env_1": {
    "api_format": "copilot",
    "base_url": "https://api.githubcopilot.com",
    "model_1": "gpt-5.4"
  },
  "model": "env_1:model_1"
}
```

**Authentication**:
```bash
illusion auth login copilot
```

---

#### 5. Alibaba Cloud DashScope

```json
{
  "env_1": {
    "api_format": "openai",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model_1": "qwen-max",
    "api_key": "sk-xxxxx"
  },
  "model": "env_1:model_1"
}
```

**Authentication**:
- Environment variable: `DASHSCOPE_API_KEY`
- Credential storage: `illusion auth login dashscope`

---

#### 6. Custom OpenAI Compatible Endpoint

```json
{
  "env_1": {
    "api_format": "openai",
    "base_url": "https://api.your-llm.com/v1",
    "model_1": "llama-3-70b",
    "api_key": "your-api-key"
  },
  "model": "env_1:model_1"
}
```

---

#### 7. Multi-Provider Mixed Configuration

Configure multiple different providers simultaneously, switch via the `model` field:

```json
{
  "env_1": {
    "api_format": "anthropic",
    "base_url": null,
    "model_1": "claude-sonnet-4-6",
    "model_2": "claude-opus-4-6",
    "api_key": "sk-ant-xxxxx"
  },
  "env_2": {
    "api_format": "openai",
    "base_url": "https://api.openai.com/v1",
    "model_1": "gpt-5.4",
    "api_key": "sk-xxxxx"
  },
  "env_3": {
    "api_format": "copilot",
    "base_url": "https://api.githubcopilot.com",
    "model_1": "gpt-5.5"
  },
  "model": "env_1:model_1"
}
```

**Switching methods**:
```bash
# Use /model command to switch interactively
/model

# Use -m parameter to specify directly
illusion -m env_2:model_1
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

Configure in the `mcp_servers` field of `~/.illusion/settings.json`, applies to all projects:

```json
{
  "mcp_servers": {
    "solidworks": {
      "type": "stdio",
      "command": "python",
      "args": ["E:\\claudecode\\SolidWorks-MCP\\server.py"]
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
  "args": ["E:\\claudecode\\SolidWorks-MCP\\server.py"]
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
| `stdio` | command, args, env, cwd | Communication via standard input/output |
| `http` | url, headers | Communication via HTTP protocol |
| `ws` | url, headers | Communication via WebSocket protocol |

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

Hooks allow executing custom operations when specific events occur.

#### Supported Hook Types

| Hook Event | Description |
|------------|-------------|
| `PRE_TOOL_USE` | Before tool execution |
| `POST_TOOL_USE` | After tool execution |
| `USER_PROMPT_SUBMIT` | After user prompt submission |

#### Hook Configuration Example

```json
{
  "hooks": {
    "PRE_TOOL_USE": [
      {
        "type": "command",
        "command": "echo 'Tool: $TOOL_NAME' >> /tmp/tool.log",
        "timeout_seconds": 30,
        "block_on_failure": false
      }
    ],
    "POST_TOOL_USE": [
      {
        "type": "http",
        "url": "https://hooks.example.com/tool-complete",
        "headers": {"Authorization": "Bearer token"},
        "timeout_seconds": 10
      }
    ],
    "USER_PROMPT_SUBMIT": [
      {
        "type": "prompt",
        "prompt": "Check if user input contains sensitive information",
        "block_on_failure": true
      }
    ]
  }
}
```

#### Hook Type Details

| Type | Required Fields | Optional Fields | Description |
|------|-----------------|-----------------|-------------|
| `command` | command | timeout_seconds, matcher, block_on_failure | Execute Shell command |
| `prompt` | prompt | model, timeout_seconds, matcher, block_on_failure | Use LLM for verification |
| `http` | url | headers, timeout_seconds, matcher, block_on_failure | Send HTTP request |
| `agent` | prompt | model, timeout_seconds, matcher, block_on_failure | Use Agent for verification |

---

### Environment Variables

Supported environment variables:

| Variable Name | Description |
|---------------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `DASHSCOPE_API_KEY` | Alibaba Cloud DashScope API key |
| `ANTHROPIC_MODEL` / `illusion_MODEL` | Default model |
| `ANTHROPIC_BASE_URL` / `illusion_BASE_URL` | API endpoint |
| `illusion_MAX_TOKENS` | Maximum token count |
| `illusion_MAX_TURNS` | Maximum conversation turns |
| `illusion_API_FORMAT` | API format |
| `illusion_PROVIDER` | Provider |
| `illusion_SANDBOX_ENABLED` | Whether to enable sandbox |
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

```json
{
  "sandbox": {
    "enabled": true,
    "fail_if_unavailable": false,
    "enabled_platforms": ["linux", "darwin"],
    "network": {
      "allowed_domains": ["api.anthropic.com"],
      "denied_domains": ["internal.company.com"]
    },
    "filesystem": {
      "allow_read": ["./src", "./docs"],
      "deny_read": ["./secrets"],
      "allow_write": ["./output"],
      "deny_write": ["./.git"]
    }
  }
}
```

---

## 🔌 Extension Development

### Hook System

Supports multiple hook types:

- `PRE_TOOL_USE` - Before tool execution
- `POST_TOOL_USE` - After tool execution
- `USER_PROMPT_SUBMIT` - After user prompt submission

### Plugin System

Defined through `plugin.json` manifest:

- Skills
- Commands
- Hooks
- MCP Servers

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
