# Command System

## Main Command-Line Options

The `illusion` main command supports the following options, grouped by function:

### Session

| Option | Short | Description |
|--------|-------|-------------|
| `--continue` | `-c` | Continue the most recent conversation in the current directory |
| `--resume [SESSION_ID]` | `-r` | Resume a conversation by session ID; opens picker if no value given |
| `--name <NAME>` | `-n` | Set a display name for this session (stored in `tool_metadata.session_name`) |

### Model & Effort

| Option | Short | Description |
|--------|-------|-------------|
| `--model <MODEL>` | `-m` | Model alias (e.g. `sonnet`, `opus`) or full model ID (e.g. `env_1.model_2`) |
| `--effort <LEVEL>` | - | Effort level: `low` / `medium` / `high` / `max` |
| `--verbose` | - | Override verbose mode setting from config, enable INFO-level logging |
| `--max-turns <N>` | - | Maximum number of agentic turns (especially useful with `--print`) |

### Output

| Option | Short | Description |
|--------|-------|-------------|
| `--print <PROMPT>` | `-p` | Non-interactive print mode: execute a single prompt and exit |
| `--output-format <FORMAT>` | - | Output format for `--print` mode: `text` (default) / `json` / `stream-json` |

### Permissions

| Option | Description |
|--------|-------------|
| `--permission-mode <MODE>` | Permission mode: `default` / `plan` / `full_auto` |
| `--dangerously-skip-permissions` | Bypass all permission checks (equivalent to `--permission-mode full_auto`, only for sandboxed environments) |
| `--allowed-tools <TOOLS...>` | Tool whitelist (space or comma separated), keep only the specified tools |
| `--disallowed-tools <TOOLS...>` | Tool blacklist (space or comma separated), remove the specified tools |

### System & Context

| Option | Short | Description |
|--------|-------|-------------|
| `--system-prompt <PROMPT>` | `-s` | Fully override the default system prompt |
| `--append-system-prompt <TEXT>` | - | Append text to the default system prompt (does not override the original) |
| `--settings <PATH_OR_JSON>` | - | Path to a JSON settings file or an inline JSON string |
| `--base-url <URL>` | - | Anthropic-compatible API base URL |
| `--api-key <KEY>` | `-k` | API key (overrides config and environment variables) |
| `--bare` | - | Minimal mode: skip hooks, plugins, MCP auto-discovery |
| `--api-format <FORMAT>` | - | API format: `anthropic` (default) or `openai` (DashScope, GitHub Models, etc.) |

### Advanced

| Option | Short | Description |
|--------|-------|-------------|
| `--debug` | `-d` | Enable DEBUG-level logging |
| `--mcp-config <CONFIG...>` | - | Load MCP servers from JSON files or strings (can be specified multiple times) |

### Global

| Option | Short | Description |
|--------|-------|-------------|
| `--version` | `-v` | Show version and exit |
| `--help` | `-h` | Show help and exit |

### Run Modes

`illusion` supports three main run modes:

#### 1. Interactive Session Mode (default)

```bash
illusion                            # Start interactive session
illusion -m env_1.model_2           # Start with a specific model
illusion --permission-mode full_auto  # Start with auto permission mode
illusion --verbose                  # Start with verbose logging
illusion --bare                     # Start in minimal mode (no plugins/MCP/hooks)
```

#### 2. Non-Interactive Print Mode

```bash
illusion -p "Analyze the project structure"
illusion -p "say hi" --output-format json
illusion -p "refactor this" --max-turns 10
```

#### 3. Session Resume Mode

```bash
illusion -c                         # Continue the most recent session
illusion --resume                   # Open the session picker
illusion --resume <session-id>      # Resume a specific session
illusion -c --name "feature-work"   # Continue a session and name it
```

### Parameter Pass-Through

All main command options are fully passed through to the React terminal frontend (`launch_react_tui` → `build_backend_command`) and the structured backend host (`run_backend_host` → `build_runtime`), ensuring they take effect in interactive mode, the `--backend-only` subprocess mode, and `-c`/`--resume` session resume mode.

### Common Combinations

```bash
# Model + permission mode + appended system prompt
illusion -m env_1.model_2 --permission-mode plan --append-system-prompt "Always respond in Chinese"

# Minimal mode + extra MCP config
illusion --bare --mcp-config '{"mcpServers": {"my-server": {"type": "stdio", "command": "node", "args": ["server.js"]}}}'

# Tool whitelist (only bash and file read)
illusion --allowed-tools bash read_file

# Tool blacklist (disable bash and powershell)
illusion --disallowed-tools bash powershell

# Custom settings file + API format
illusion --settings /path/to/custom.json --api-format openai

# Debug mode + verbose logging
illusion --debug --verbose

# Name a session
illusion --name "debug-auth-issue"
```

### `--mcp-config` Format

`--mcp-config` accepts two input forms:

**JSON string** (supports single-server or multi-server format):

```bash
# Multi-server format
illusion --mcp-config '{"mcpServers": {"server1": {"type": "stdio", "command": "node", "args": ["s1.js"]}, "server2": {"type": "stdio", "command": "python", "args": ["s2.py"]}}}'

# Single-server format
illusion --mcp-config '{"type": "stdio", "command": "node", "args": ["server.js"]}'

# snake_case key is also supported
illusion --mcp-config '{"mcp_servers": {"my-server": {...}}}'
```

**JSON file path** (file is read automatically when the path exists):

```bash
illusion --mcp-config /path/to/mcp-servers.json
```

`--mcp-config` can be specified multiple times to load multiple config sources. Compatible with `--bare` mode: `--bare` skips auto-discovered MCP servers, but `--mcp-config` explicitly specified servers are still loaded.

## Subcommands

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

# Channel management (Feishu/WeChat/QQ messaging)
illusion channel login           # Interactive channel setup (select channel → configure credentials)
illusion channel serve           # Run channel daemon in foreground (listen for messages)
illusion channel status          # View channel status (enabled/connected/PID)
illusion channel enable feishu   # Enable a channel
illusion channel disable feishu  # Disable a channel
illusion channel logout feishu   # Clear channel credentials

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

## Interactive Slash Commands

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
