---
name: update-config
description: Configure Illusion Code via settings.json. Use for permissions, hooks, env vars, MCP servers, sandbox, and other settings. Examples: "allow npm commands", "set DEBUG=true", "add a hook to format code after writes".
---

# Update Config Skill

Modify Illusion Code configuration by updating `~/.illusion/settings.json`.

## CRITICAL: Read Before Write

**Always read the existing settings file before making changes.** Merge new settings with existing ones - never replace the entire file.

## CRITICAL: Use `ask_user_question` for Ambiguity

When the user's request is ambiguous, use `ask_user_question` to clarify:
- Specific values when multiple options exist
- Whether to add to existing arrays or replace them

## Settings File Location

| File | Scope | Path |
|------|-------|------|
| `settings.json` | Global (all projects) | `~/.illusion/settings.json` |
| `credentials.json` | Global (API keys) | `~/.illusion/credentials.json` |

> **Note:** Configuration is global only (`~/.illusion/settings.json`). There is no project-level `settings.json` merge. Use `CLAUDE.md` / `ILLUSION.md` / `AGENTS.md` files in the project root for project-specific instructions (not config).

Environment variable overrides: `ILLUSION_CONFIG_DIR` replaces `~/.illusion/`, `ILLUSION_DATA_DIR` replaces `~/.illusion/data/`, `ILLUSION_LOGS_DIR` replaces `~/.illusion/logs/`.

Configuration priority: CLI arguments > settings.json > built-in defaults.

## When Hooks Are Required

If the user wants something to happen automatically in response to an EVENT, they need a **hook** configured in settings.json.

**These require hooks:**
- "After writing files, run prettier" → `post_tool_use` hook with matcher `write_file|edit_file`
- "Before running bash commands, validate them" → `pre_tool_use` hook with matcher `bash`
- "When session starts, show a greeting" → `session_start` hook

**Hook events (only 4):**
- `session_start` — When session starts
- `session_end` — When session ends
- `pre_tool_use` — Before tool execution (can block)
- `post_tool_use` — After tool execution

## Settings Schema Reference

### Complete Configuration Structure

```json
{
  "env_1": {
    "api_format": "anthropic",
    "base_url": null,
    "api_key": "",
    "system_prompt": null,
    "model_1": "claude-sonnet-4-6",
    "model_2": "claude-opus-4-6"
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
  "working_directory": null,
  "ui_language": "en-US",
  "output_style": "default",
  "show_thinking": true,
  "fast_mode": false,
  "effort": "medium",
  "passes": 1,
  "verbose": false
}
```

### Top-Level Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `env_N` | object | - | Environment config group (EnvConfig) |
| `model` | string | "env_1.model_1" | Active model reference: `env_N.model_N` |
| `context_window` | int | 200000 | Context window size in tokens |
| `system_prompt` | string\|null | null | Custom global system prompt (overridable per env_N) |
| `max_tokens` | int | 16384 | Maximum output tokens |
| `max_turns` | int | 200 | Maximum conversation turns |
| `ui_language` | string | "en-US" | UI language ("en-US" / "zh-CN") |
| `output_style` | string | "default" | Output style name |
| `show_thinking` | bool | true | Show thinking process |
| `fast_mode` | bool | false | Fast mode |
| `effort` | string | "medium" | Reasoning effort: low/medium/high/xhigh/max |
| `passes` | int | 1 | Reasoning passes (1-8) |
| `verbose` | bool | false | Verbose output |
| `working_directory` | string\|null | null | Fixed working directory (auto-switch on startup) |
| `enabled_plugins` | object | {} | Plugin enable/disable map |
| `mcp_servers` | object | {} | MCP server configurations |

### Environment Configuration (env_N)

Each `env_N` is an independent API provider config. Models are referenced as `env_N.model_N`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `api_format` | string | Yes | API format: `anthropic` / `openai` / `copilot` / `codex` |
| `base_url` | string\|null | No | Custom API endpoint, null uses default |
| `api_key` | string | No | API key (or use `illusion auth login` for credentials.json) |
| `system_prompt` | string\|null | No | Per-environment system prompt (overrides global) |
| `model_N` | string | No | Model name: `model_1`, `model_2`, ... |

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
  "model": "env_1.model_1"
}
```

**API key storage priority:** `env_N.api_key` (in settings.json) > `credentials.json` (managed by `illusion auth login`).

### Permissions

```json
{
  "permission": {
    "mode": "default",
    "allowed_tools": ["bash(npm:*)", "read_file", "grep"],
    "denied_tools": ["bash(rm -rf:*)"],
    "denied_commands": ["git push --force"],
    "path_rules": [
      {"pattern": ".env*", "allow": false},
      {"pattern": "src/**", "allow": true}
    ]
  }
}
```

**Permission modes (only 3):**
| Mode | Value | Description |
|------|-------|-------------|
| Default | `default` | Modification tools require user confirmation |
| Plan | `plan` | Block all modification tools |
| Full Auto | `full_auto` | Allow all operations automatically |

> **Note:** `accept_edits` and `dont_ask` modes do NOT exist. Use `full_auto` for automatic execution.

**Tool names** (lowercase, used in matchers):
- `bash` — Shell commands
- `read_file` — Read file contents
- `edit_file` — Edit existing file
- `write_file` — Write/create file
- `grep` — Search file contents
- `glob` — Find files by pattern

**Permission Rule Syntax:**
- Exact match: `"bash(npm run test)"`
- Prefix wildcard: `"bash(git:*)"` - matches `git status`, `git commit`, etc.
- Tool only: `"read_file"` - allows all read_file operations

### Hooks

```json
{
  "hooks": {
    "pre_tool_use": [
      {
        "type": "command",
        "command": "echo 'Tool called'",
        "timeout_seconds": 30,
        "matcher": "bash",
        "block_on_failure": false
      }
    ],
    "post_tool_use": [
      {
        "type": "command",
        "command": "prettier --write $FILE",
        "timeout_seconds": 30,
        "matcher": "write_file|edit_file"
      }
    ]
  }
}
```

#### Hook Types (4)

**1. Command Hook** — Runs a shell command:
```json
{
  "type": "command",
  "command": "prettier --write $FILE",
  "timeout_seconds": 30,
  "matcher": "write_file|edit_file",
  "block_on_failure": false
}
```

**2. Prompt Hook** — Uses LLM to evaluate a condition:
```json
{
  "type": "prompt",
  "prompt": "Is this command safe? $ARGUMENTS",
  "model": "env_1.model_1",
  "timeout_seconds": 30,
  "matcher": "bash",
  "block_on_failure": true
}
```

**3. HTTP Hook** — Sends event payload to an HTTP endpoint:
```json
{
  "type": "http",
  "url": "https://example.com/webhook",
  "headers": {"Authorization": "Bearer token"},
  "timeout_seconds": 30,
  "matcher": "write_file|edit_file",
  "block_on_failure": false
}
```

**4. Agent Hook** — Uses an agent for deep validation:
```json
{
  "type": "agent",
  "prompt": "Verify this change is safe: $ARGUMENTS",
  "model": "env_1.model_1",
  "timeout_seconds": 60,
  "matcher": "write_file|edit_file",
  "block_on_failure": true
}
```

#### Hook Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | string | required | Hook type: `command`, `prompt`, `http`, `agent` |
| `command` | string | (command) | Shell command to execute |
| `prompt` | string | (prompt/agent) | Prompt for LLM evaluation |
| `url` | string | (http) | HTTP endpoint URL |
| `headers` | object | `{}` | HTTP headers |
| `model` | string | null | Model override as `env_N.model_N` (prompt/agent) |
| `timeout_seconds` | int | 30/60 | Timeout in seconds |
| `matcher` | string | null | Tool name pattern to match (lowercase) |
| `block_on_failure` | bool | varies | Block execution on failure |

#### Hook Input (stdin JSON)

Hooks receive JSON on stdin:
```json
{
  "session_id": "abc123",
  "tool_name": "write_file",
  "tool_input": { "file_path": "/path/to/file.txt", "content": "..." },
  "tool_response": { "success": true }
}
```

#### Hook Output

Command hooks can output JSON to control behavior:
```json
{
  "blocked": true,
  "reason": "Command not allowed",
  "output": "Detailed explanation"
}
```

- `blocked` — Set to `true` to block the tool execution
- `reason` — Message shown when blocking
- `output` — Output text (displayed to user or injected as context)

### Memory

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
| `enabled` | true | Enable memory function |
| `max_files` | 5 | Maximum number of memory files |
| `max_entrypoint_lines` | 200 | Maximum lines for MEMORY.md entry file |

### Sandbox

The sandbox provides OS-level isolation for shell commands. Supports Linux (bubblewrap), macOS (seatbelt), and Windows (Job Objects).

```json
{
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
  }
}
```

#### Network Configuration
```json
{
  "sandbox": {
    "network": {
      "allowed_domains": ["api.anthropic.com", "*.github.com"],
      "denied_domains": ["malicious.example.com"],
      "allow_local_binding": false
    }
  }
}
```

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

#### Excluded Commands
```json
{
  "sandbox": {
    "excluded_commands": ["npm test", "make:*", "git status"]
  }
}
```

### MCP Servers

```json
{
  "mcp_servers": {
    "server-name": {
      "command": "node",
      "args": ["server.js"],
      "env": {}
    }
  }
}
```

> `mcpServers` (camelCase) is also accepted for backward compatibility and auto-mapped to `mcp_servers`.

## Common Patterns

### Auto-format after writes
```json
{
  "hooks": {
    "post_tool_use": [{
      "type": "command",
      "command": "jq -r '.tool_input.file_path // .tool_response.filePath' | { read -r f; prettier --write \"$f\"; } 2>/dev/null || true",
      "matcher": "write_file|edit_file",
      "timeout_seconds": 30
    }]
  }
}
```

### Log all bash commands
```json
{
  "hooks": {
    "pre_tool_use": [{
      "type": "command",
      "command": "jq -r '.tool_input.command' >> ~/.illusion/bash-log.txt",
      "matcher": "bash"
    }]
  }
}
```

### Block dangerous commands
```json
{
  "hooks": {
    "pre_tool_use": [{
      "type": "command",
      "command": "jq -r '.tool_input.command' | grep -qE 'rm -rf|drop table' && echo '{\"blocked\": true, \"reason\": \"Dangerous command blocked\"}' || true",
      "matcher": "bash",
      "block_on_failure": false
    }]
  }
}
```

### Allow specific bash commands
```json
{
  "permission": {
    "allowed_tools": ["bash(npm:*)", "bash(git:*)", "read_file", "grep", "glob"]
  }
}
```

### Deny destructive commands
```json
{
  "permission": {
    "denied_tools": ["bash(rm -rf:*)"],
    "denied_commands": ["git push --force", "git reset --hard"]
  }
}
```

### Protect sensitive files
```json
{
  "permission": {
    "path_rules": [
      {"pattern": ".env*", "allow": false},
      {"pattern": "secrets/**", "allow": false},
      {"pattern": "src/**", "allow": true}
    ]
  }
}
```

## Workflow

1. **Clarify intent** — Ask if the request is ambiguous
2. **Read existing file** — Use Read tool on `~/.illusion/settings.json`
3. **Merge carefully** — Preserve existing settings, especially arrays
4. **Edit file** — Use Edit tool (if file doesn't exist, create it first)
5. **Validate** — Check JSON syntax
6. **Confirm** — Tell user what was changed

## Merging Arrays (Important!)

When adding to permission arrays or hook arrays, **merge with existing**, don't replace:

**WRONG** (replaces existing):
```json
{ "permission": { "allowed_tools": ["bash(npm:*)"] } }
```

**RIGHT** (preserves existing + adds new):
```json
{
  "permission": {
    "allowed_tools": [
      "bash(git:*)",
      "read_file",
      "bash(npm:*)"
    ]
  }
}
```

## Troubleshooting

If a hook isn't running:
1. Check the settings file exists and has valid JSON
2. Verify the event name is correct (lowercase with underscores: `pre_tool_use`, `post_tool_use`, `session_start`, `session_end`)
3. Check the matcher matches the tool name (lowercase: `bash`, `write_file`, `edit_file`, etc.)
4. Check hook type is one of: `command`, `prompt`, `http`, `agent`
5. Test the command manually
6. Check `timeout_seconds` isn't too low

If permissions aren't working:
1. Verify mode is one of: `default`, `plan`, `full_auto` (no other modes exist)
2. Check tool names are lowercase: `bash`, `read_file`, `edit_file`, `write_file`, `grep`, `glob`
3. Check rule syntax: `bash(command:*)` for prefix match, `bash(exact command)` for exact match
