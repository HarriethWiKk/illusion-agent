# 设置与凭据配置

## 目录

- [配置概览](#配置概览)
- [凭据文件 (credentials.json)](#凭据文件-credentialsjson)
- [全局配置 (settings.json)](#全局配置-settingsjson)
  - [working_directory](#working_directory)
  - [环境配置 (EnvConfig)](#环境配置-envconfig)
  - [各 API 格式配置示例](#各-api-格式配置示例)
  - [权限配置](#权限配置)
  - [环境变量](#环境变量)
  - [记忆系统配置](#记忆系统配置)
  - [沙箱配置](#沙箱配置)

---

## 配置概览

| 文件 | 位置 | 作用域 | 用途 |
|------|------|--------|------|
| `settings.json` | `~/.illusion/settings.json` | 全局 | 主设置：API 配置、权限、钩子等 |
| `credentials.json` | `~/.illusion/credentials.json` | 全局 | 安全凭据存储（API 密钥） |

环境变量覆盖：`ILLUSION_CONFIG_DIR` 替换 `~/.illusion/`，`ILLUSION_DATA_DIR` 替换 `~/.illusion/data/`，`ILLUSION_LOGS_DIR` 替换 `~/.illusion/logs/`。

### 配置优先级

1. **CLI 参数** — 最高优先级
2. **配置文件** — `~/.illusion/settings.json`
3. **默认值** — 内置默认配置

---

## 凭据文件 (credentials.json)

位于 `~/.illusion/credentials.json`，由 `illusion auth login` 管理。凭据按 `env_N` 分组存储。

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

**API 密钥存储方式：**

| 方式 | 位置 | 优势 |
|------|------|------|
| **安全模式** | `credentials.json`（由 `illusion auth login` 管理） | 密钥与配置分离，文件权限受保护 |
| **便捷模式** | `settings.json` 的 `env_N.api_key` | 配置集中在一个文件 |

运行时优先级：`env_N.api_key` > `credentials.json`。

> **文件权限 600**：在 Unix/Linux 上，文件设置为 `rw-------`（仅所有者可读写）。Windows 上静默跳过。

---

## 全局配置 (settings.json)

### 格式

使用 `env_N` 分组格式。每个 `env_N` 是独立的环境配置（EnvConfig）。`model` 字段引用 `env_N.model_N`。

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

### 完整配置结构

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
  "ui_language": "zh-CN",
  "output_style": "default",
  "effort": "medium",
  "passes": 1
}
```

### 配置字段说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `env_N` | object | - | 环境配置组（EnvConfig） |
| `model` | string | "env_1.model_1" | 当前活跃模型引用：`env_N.model_N` |
| `context_window` | int | 200000 | 上下文窗口大小（tokens） |
| `system_prompt` | string\|null | null | 自定义系统提示词（全局，可被 env_N 覆盖） |
| `max_tokens` | int | 16384 | 最大输出 token 数 |
| `max_turns` | int | 200 | 最大对话轮数 |
| `ui_language` | string | "zh-CN" | 界面语言 |
| `effort` | string | "medium" | 推理强度：low/medium/high/xhigh/max |
| `passes` | int | 1 | 推理轮数（1-8） |
| `working_directory` | string | - | 固定工作目录（可选） |

---

## working_directory

固定工作目录。如果设置此字段，illusion-agent启动时会自动切换到该目录。

**类型：** 字符串（可选）

**默认值：** 不设置或为空

**示例：**

```json
{
  "working_directory": "E:\\Projects\\my-project"
}
```

**行为：**
- 如果字段存在且不为空，启动时自动切换到指定目录
- 如果字段不存在或为空，使用启动时的当前目录
- 如果指定的目录不存在或无权限，记录警告日志，使用当前目录

---

### 环境配置 (EnvConfig)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `api_format` | string | 是 | API 格式：`anthropic` / `openai` / `copilot` / `codex` |
| `base_url` | string\|null | 否 | 自定义 API 端点，null 使用默认端点 |
| `api_key` | string | 否 | API 密钥（标准 x-api-key 认证） |
| `auth_token` | string | 否 | Bearer Token 认证（用于 LongCat 等使用 `Authorization: Bearer` 的提供商） |
| `system_prompt` | string\|null | 否 | 该环境的系统提示词（覆盖全局） |
| `model_N` | string | 否 | 模型名称：`model_1`、`model_2`、... |

### 多模型配置

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

**切换模型：**
```bash
/model                          # 交互式切换
illusion -m env_1.model_2       # CLI 参数指定
```

---

### 各 API 格式配置示例

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

#### 3. 自定义格式

在 `illusion auth login` 中选择"自定义格式"，输入 API 格式、端点、密钥和模型名。

#### 4. GitHub Copilot

```bash
illusion auth login  # 选择 GitHub Copilot
```

在浏览器中完成 GitHub 授权后自动配置。认证数据存储在 `~/.illusion/copilot_auth.json`。

```json
{
  "env_1": {
    "api_format": "copilot",
    "base_url": "https://api.githubcopilot.com",
    "model_1": "gpt-5.5"
  }
}
```

#### 5. OpenAI Codex（ChatGPT 订阅）

```bash
illusion auth login   # 选择 OpenAI Codex
```

使用 Device Code 流程完成 ChatGPT 订阅认证。认证数据存储在 `~/.illusion/codex_oauth_auth.json`。

```json
{
  "env_1": {
    "api_format": "codex",
    "base_url": "https://chatgpt.com/backend-api",
    "model_1": "codex-mini"
  }
}
```

#### 6. LongCat（Bearer Token 认证）

LongCat 使用 `Authorization: Bearer` 认证方式，需要通过 `auth_token` 字段配置（而非 `api_key`）。

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

#### 7. 多格式混合配置

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

### 权限配置

#### 权限模式

| 模式 | 值 | 说明 |
|------|-----|------|
| 默认模式 | `default` | 修改类工具需要用户确认 |
| 计划模式 | `plan` | 阻止所有修改类工具 |
| 全自动模式 | `full_auto` | 允许一切操作 |

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

### 环境变量

| 变量 | 说明 |
|------|------|
| `ILLUSION_CONFIG_DIR` | 覆盖配置目录路径（默认：`~/.illusion/`） |
| `ILLUSION_DATA_DIR` | 覆盖数据目录路径（默认：`~/.illusion/data/`） |
| `ILLUSION_LOGS_DIR` | 覆盖日志目录路径（默认：`~/.illusion/logs/`） |

> **注意：** API 密钥、模型名称等运行时设置仅通过 `settings.json` 和 `credentials.json` 管理。使用 `illusion auth login` 配置凭据。

---

### 记忆系统配置

```json
{
  "memory": {
    "enabled": true,
    "max_files": 5,
    "max_entrypoint_lines": 200
  }
}
```

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | true | 启用记忆功能 |
| `max_files` | 5 | 最大记忆文件数 |
| `max_entrypoint_lines` | 200 | MEMORY.md 入口文件最大行数 |

---

### 沙箱配置

沙箱系统为 shell 命令提供操作系统级隔离。支持三平台：

| 平台 | 机制 | 依赖 |
|------|------|------|
| Linux / WSL | bubblewrap (bwrap) + 可选 seccomp | `bwrap`、`socat` |
| macOS | Apple Seatbelt (sandbox-exec) | 内置 |
| Windows | Job Objects + Restricted Tokens + Low Integrity | `pywin32` |

#### 基础配置

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

#### 网络配置

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

#### 文件系统配置

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

#### 排除命令

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
