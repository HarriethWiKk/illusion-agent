---
name: update-config
description: Configure Illusion Code via settings.json. Use for permissions, hooks, env vars, MCP servers, and other settings. Examples: "allow npm commands", "set DEBUG=true", "add a hook to format code after writes".
---

# Update Config Skill

Modify Illusion Code configuration by updating settings.json files.

## When Hooks Are Required

If the user wants something to happen automatically in response to an EVENT, they need a **hook** configured in settings.json.

**These require hooks:**
- "After writing files, run prettier" → `post_tool_use` hook with matcher `Write|Edit`
- "Before running bash commands, validate them" → `pre_tool_use` hook with matcher `Bash`
- "When session starts, show a greeting" → `session_start` hook

**Hook events (only 4):**
- `session_start` — When session starts
- `session_end` — When session ends
- `pre_tool_use` — Before tool execution (can block)
- `post_tool_use` — After tool execution

## CRITICAL: Read Before Write

**Always read the existing settings file before making changes.** Merge new settings with existing ones - never replace the entire file.

## CRITICAL: Use `ask_user_question` for Ambiguity

When the user's request is ambiguous, use `ask_user_question` to clarify:
- Which settings file to modify (user/project)
- Whether to add to existing arrays or replace them
- Specific values when multiple options exist

## Settings File Locations

| File | Scope | Use For |
|------|-------|---------|
| `~/.illusion/settings.json` | Global | Personal preferences for all projects |
| `.illusion/settings.json` | Project | Team-wide hooks, permissions, plugins |

Settings load in order: user → project (later overrides earlier).

## Settings Schema Reference

### Model Configuration
```json
{
  "model": "env_1.model_1",
  "max_tokens": 16384,
  "max_turns": 200,
  "context_window": 200000,
  "effort": "medium"
}
```

The `model` field format is `env_N.model_N` referencing an environment configuration.

### Environment Configuration (env_N)
```json
{
  "env_1": {
    "api_format": "anthropic",
    "base_url": null,
    "api_key": "",
    "model_1": "claude-sonnet-4-6",
    "model_2": "claude-opus-4-6"
  }
}
```

### Permissions
```json
{
  "permission": {
    "mode": "default",
    "allowed_tools": ["Bash(npm:*)", "Edit", "Read"],
    "denied_tools": ["Bash(rm -rf:*)"],
    "denied_commands": ["git push --force"],
    "path_rules": [
      {"pattern": ".env*", "allow": false},
      {"pattern": "*.md", "allow": true}
    ]
  }
}
```

**Permission modes:** `default`, `plan`, `accept_edits`, `dont_ask`

**Permission Rule Syntax:**
- Exact match: `"Bash(npm run test)"`
- Prefix wildcard: `"Bash(git:*)"` - matches `git status`, `git commit`, etc.
- Tool only: `"Read"` - allows all Read operations

### Hooks
```json
{
  "hooks": {
    "pre_tool_use": [
      {
        "type": "command",
        "command": "echo 'Tool called'",
        "timeout_seconds": 30,
        "matcher": "Bash",
        "block_on_failure": false
      }
    ],
    "post_tool_use": [
      {
        "type": "command",
        "command": "prettier --write $FILE",
        "timeout_seconds": 30,
        "matcher": "Write|Edit"
      }
    ]
  }
}
```

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

### Other Settings
- `ui_language`: Interface language (e.g., "zh-CN", "en-US")
- `output_style`: Output style name
- `show_thinking`: Show thinking process (boolean)
- `fast_mode`: Enable fast mode (boolean)
- `verbose`: Verbose output (boolean)
- `passes`: Number of passes (integer)
- `enabled_plugins`: Plugin enable/disable map

## Hook Types

### 1. Command Hook
Runs a shell command:
```json
{
  "type": "command",
  "command": "prettier --write $FILE",
  "timeout_seconds": 30,
  "matcher": "Write|Edit",
  "block_on_failure": false
}
```

### 2. Prompt Hook
Uses LLM to evaluate a condition:
```json
{
  "type": "prompt",
  "prompt": "Is this command safe? $ARGUMENTS",
  "model": "claude-sonnet-4-6",
  "timeout_seconds": 30,
  "matcher": "Bash",
  "block_on_failure": true
}
```

### 3. HTTP Hook
Sends event payload to an HTTP endpoint:
```json
{
  "type": "http",
  "url": "https://example.com/webhook",
  "headers": {"Authorization": "Bearer token"},
  "timeout_seconds": 30,
  "matcher": "Write|Edit",
  "block_on_failure": false
}
```

### 4. Agent Hook
Uses an agent for deep validation:
```json
{
  "type": "agent",
  "prompt": "Verify this change is safe: $ARGUMENTS",
  "model": "claude-sonnet-4-6",
  "timeout_seconds": 60,
  "matcher": "Write|Edit",
  "block_on_failure": true
}
```

### Hook Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | string | required | Hook type: `command`, `prompt`, `http`, `agent` |
| `command` | string | (command) | Shell command to execute |
| `prompt` | string | (prompt/agent) | Prompt for LLM evaluation |
| `url` | string | (http) | HTTP endpoint URL |
| `headers` | object | `{}` | HTTP headers |
| `model` | string | null | Model override (prompt/agent) |
| `timeout_seconds` | int | 30/60 | Timeout in seconds |
| `matcher` | string | null | Tool name pattern to match |
| `block_on_failure` | bool | varies | Block execution on failure |

### Hook Input (stdin JSON)
Hooks receive JSON on stdin:
```json
{
  "session_id": "abc123",
  "tool_name": "Write",
  "tool_input": { "file_path": "/path/to/file.txt", "content": "..." },
  "tool_response": { "success": true }
}
```

### Hook Output

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

## Common Patterns

### Auto-format after writes
```json
{
  "hooks": {
    "post_tool_use": [{
      "type": "command",
      "command": "jq -r '.tool_input.file_path // .tool_response.filePath' | { read -r f; prettier --write \"$f\"; } 2>/dev/null || true",
      "matcher": "Write|Edit",
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
      "matcher": "Bash"
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
      "matcher": "Bash",
      "block_on_failure": false
    }]
  }
}
```

## Workflow

1. **Clarify intent** — Ask if the request is ambiguous
2. **Read existing file** — Use Read tool on the target settings file
3. **Merge carefully** — Preserve existing settings, especially arrays
4. **Edit file** — Use Edit tool (if file doesn't exist, create it first)
5. **Validate** — Check JSON syntax
6. **Confirm** — Tell user what was changed

## Merging Arrays (Important!)

When adding to permission arrays or hook arrays, **merge with existing**, don't replace:

**WRONG** (replaces existing):
```json
{ "permission": { "allowed_tools": ["Bash(npm:*)"] } }
```

**RIGHT** (preserves existing + adds new):
```json
{
  "permission": {
    "allowed_tools": [
      "Bash(git:*)",
      "Edit",
      "Bash(npm:*)"
    ]
  }
}
```

## Troubleshooting

If a hook isn't running:
1. Check the settings file exists and has valid JSON
2. Verify the event name is correct (lowercase with underscores)
3. Check the matcher matches the tool name
4. Check hook type is one of: `command`, `prompt`, `http`, `agent`
5. Test the command manually
6. Check `timeout_seconds` isn't too low
