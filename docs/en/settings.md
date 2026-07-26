# Settings & Credentials

## Table of Contents

- [Configuration Overview](#configuration-overview)
- [Credentials File (credentials.json)](#credentials-file-credentialsjson)
- [Global Configuration (settings.json)](#global-configuration-settingsjson)
  - [working_directory](#working_directory)
  - [Environment Configuration (EnvConfig)](#environment-configuration-envconfig)
  - [API Format Configuration Examples](#api-format-configuration-examples)
  - [Permission Configuration](#permission-configuration)
  - [Environment Variables](#environment-variables)
  - [Memory System Configuration](#memory-system-configuration)
  - [Sandbox Configuration](#sandbox-configuration)

---

## Configuration Overview

| File | Location | Scope | Purpose |
|------|----------|-------|---------|
| `settings.json` | `~/.illusion/settings.json` | Global | Main settings: API config, permissions, hooks, etc. |
| `credentials.json` | `~/.illusion/credentials.json` | Global | Secure credential storage (API keys) |

Environment variable overrides: `ILLUSION_CONFIG_DIR` replaces `~/.illusion/`, `ILLUSION_DATA_DIR` replaces `~/.illusion/data/`, `ILLUSION_LOGS_DIR` replaces `~/.illusion/logs/`.

### Configuration Priority

1. **CLI Arguments** — highest priority
2. **Configuration Files** — `~/.illusion/settings.json`
3. **Default Values** — built-in defaults

---

## Credentials File (credentials.json)

Located at `~/.illusion/credentials.json`, managed by `illusion auth login`. Credentials are stored by `env_N` groups.

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

**API Key Storage Options:**

| Method | Location | Advantage |
|--------|----------|-----------|
| **Secure mode** | `credentials.json` (managed by `illusion auth login`) | Keys separated from config, file permissions protected |
| **Convenient mode** | `env_N.api_key` in `settings.json` | All config in one file |

Runtime priority: `env_N.api_key` > `credentials.json`.

> **File Permission 600**: On Unix/Linux, file is set to `rw-------` (owner only). Silently skipped on Windows.

---

## Global Configuration (settings.json)

### Format

Uses `env_N` grouped format. Each `env_N` is an independent environment config (EnvConfig). The `model` field references `env_N.model_N`.

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

### Complete Configuration Structure

```json
{
  "env_1": {
    "api_format": "anthropic",
    "base_url": null,
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
  "effort": "medium",
  "passes": 1,
  "verbose": false
}
```

### Configuration Field Description

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `env_N` | object | - | Environment config group (EnvConfig) |
| `model` | string | "env_1.model_1" | Active model reference: `env_N.model_N` |
| `context_window` | int | 200000 | Context window size in tokens |
| `system_prompt` | string\|null | null | Custom system prompt (global; overridable per env_N) |
| `max_tokens` | int | 16384 | Maximum output tokens |
| `max_turns` | int | 200 | Maximum conversation turns |
| `ui_language` | string | "en-US" | UI language |
| `effort` | string | "medium" | Reasoning effort: low/medium/high/xhigh/max |
| `passes` | int | 1 | Reasoning passes (1-8) |
| `verbose` | bool | false | Verbose output |
| `working_directory` | string | - | Fixed working directory (optional) |

---

## working_directory

Fixed working directory. If set, illusion-code will automatically switch to this directory on startup.

**Type:** String (optional)

**Default:** Not set or empty

**Example:**

```json
{
  "working_directory": "E:\\Projects\\my-project"
}
```

**Behavior:**
- If the field exists and is not empty, automatically switches to the specified directory on startup
- If the field does not exist or is empty, uses the current directory at startup
- If the specified directory does not exist or lacks permissions, logs a warning and uses the current directory

---

### Environment Configuration (EnvConfig)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `api_format` | string | Yes | API format: `anthropic` / `openai` / `copilot` / `codex` |
| `base_url` | string\|null | No | Custom API endpoint, null uses default |
| `api_key` | string | No | API key (standard `x-api-key` auth) |
| `auth_token` | string | No | Bearer Token auth (for providers like LongCat using `Authorization: Bearer`) |
| `system_prompt` | string\|null | No | Per-environment system prompt (overrides global) |
| `model_N` | string | No | Model name: `model_1`, `model_2`, ... |

### Multi-Model Configuration

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

**Switching models:**
```bash
/model                          # Interactive switch
illusion -m env_1.model_2       # CLI parameter
```

---

### API Format Configuration Examples

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

#### 3. Custom Format

Select "Custom format" in `illusion auth login`, enter API format, endpoint, API key, and model name.

#### 4. GitHub Copilot

```bash
illusion auth login  # Select GitHub Copilot
```

After GitHub authorization in browser, auto-configured. Auth stored in `~/.illusion/copilot_auth.json`.

```json
{
  "env_1": {
    "api_format": "copilot",
    "base_url": "https://api.githubcopilot.com",
    "model_1": "gpt-5.5"
  }
}
```

#### 5. OpenAI Codex (ChatGPT Subscription)

```bash
illusion auth login   # Select OpenAI Codex
```

Uses ChatGPT subscription auth via Device Code flow. Auth stored in `~/.illusion/codex_oauth_auth.json`.

```json
{
  "env_1": {
    "api_format": "codex",
    "base_url": "https://chatgpt.com/backend-api",
    "model_1": "codex-mini"
  }
}
```

#### 6. LongCat (Bearer Token Authentication)

LongCat uses `Authorization: Bearer` authentication, configured via the `auth_token` field (not `api_key`).

```json
{
  "env_1": {
    "api_format": "anthropic",
    "base_url": "https://api.longcat.chat/anthropic",
    "auth_token": "ak_your_longcat_api_key",
    "model_1": "LongCat-2.0"
  }
}
```

#### 7. Multi-Format Mixed Configuration

```json
{
  "env_1": {
    "api_format": "anthropic",
    "base_url": null,
    "model_1": "claude-sonnet-4-6"
  },
  "env_2": {
    "api_format": "openai",
    "base_url": "https://api.openai.com/v1",
    "model_1": "gpt-5.4"
  },
  "env_3": {
    "api_format": "copilot",
    "base_url": "https://api.githubcopilot.com",
    "model_1": "gpt-5.5"
  },
  "model": "env_1.model_1"
}
```

---

### Permission Configuration

#### Permission Modes

| Mode | Value | Description |
|------|-------|-------------|
| Default | `default` | Modification tools require user confirmation |
| Plan | `plan` | Block all modification tools |
| Full Auto | `full_auto` | Allow all operations |

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

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ILLUSION_CONFIG_DIR` | Override configuration directory (default: `~/.illusion/`) |
| `ILLUSION_DATA_DIR` | Override data directory (default: `~/.illusion/data/`) |
| `ILLUSION_LOGS_DIR` | Override logs directory (default: `~/.illusion/logs/`) |

> **Note:** API keys, model names, and other runtime settings are managed exclusively through `settings.json` and `credentials.json`. Use `illusion auth login` to configure credentials.

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
| `enabled` | true | Enable memory function |
| `max_files` | 5 | Maximum number of memory files |
| `max_entrypoint_lines` | 200 | Maximum lines for MEMORY.md entry file |

---

### Sandbox Configuration

The sandbox system provides OS-level isolation for shell commands. Supports three platforms:

| Platform | Mechanism | Dependencies |
|----------|-----------|--------------|
| Linux / WSL | bubblewrap (bwrap) + optional seccomp | `bwrap`, `socat` |
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
    "excluded_commands": [
      "npm test",
      "make:*",
      "git status"
    ]
  }
}
```
