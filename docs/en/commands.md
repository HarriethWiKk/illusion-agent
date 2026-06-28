# Command System

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
