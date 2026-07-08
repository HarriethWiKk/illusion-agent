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
| `--effort <LEVEL>` | `-e` | Effort level: `low` / `medium` / `high` / `max`, persists to settings.json |
| `--max-turns <N>` | `-t` | Maximum agentic turns, persists to settings.json |

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
illusion -e high                    # Start with high effort (persists to settings)
```

#### 2. Non-Interactive Print Mode

```bash
illusion -p "Analyze the project structure"
illusion -p "say hi" --output-format json
illusion -p "refactor this" -t 10
illusion -e high -p "Analyze code"  # Persist effort and execute
```

#### 3. Session Resume Mode

```bash
illusion -c -p "Continue analysis"           # Continue the most recent session (requires -p)
illusion -r <session-id> -p "Continue"       # Resume a specific session (requires -p)
illusion -c -p "Continue" --name "feature-work"  # Continue and name the session
```

Note: `-c`/`-r` now require `-p`; otherwise an error is raised. The `--resume` picker mode (no value) has been removed (non-backend-only path).

### Parameter Pass-Through

Core command options (model/effort/max_turns/permission_mode/name/continue/resume) are fully passed through to the React terminal frontend (`launch_react_tui` → `build_backend_command`) and the structured backend host (`run_backend_host` → `build_runtime`), ensuring they take effect in interactive mode, the `--backend-only` subprocess mode, and `-c`/`-r` session resume mode.

### Common Combinations

```bash
# Model + permission mode
illusion -m env_1.model_2 --permission-mode plan

# High effort + print mode (persists effort)
illusion -e high -p "Analyze performance bottlenecks in this code"

# Limit turns + print mode (persists max_turns)
illusion -t 5 -p "Quick syntax check"

# Continue session + print mode
illusion -c -p "Continue the previous task"

# Name a session
illusion --name "debug-auth-issue"
```

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
