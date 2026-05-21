# IllusionCode

<div align="center">

**AI 驱动的命令行编程助手**

*集百家之所长，融会贯通的智能编程工具*

中文 | [English](README_en.md)

</div>

---

## 📖 项目简介

IllusionCode 是一个开源的 AI 驱动命令行编程助手，集成了众多优秀项目的精华并加以创新。它继承了 Claude Code 的完整提示词体系和工具架构，在 Python 架构设计上借鉴了 OpenHarness 的理念，采用与 OpenClaw 相同的 Cron 任务调度架构，并通过 cc-switch 反代方案实现了灵活的代理路由。在此基础上，IllusionCode 针对 Windows 系统进行了深度优化，提供了完整的中英双语界面支持，并实现了比同类项目更全面的 Markdown 终端渲染能力。

### 核心特性

- 🪟 **Windows 系统深度优化** - 自动查找 Git、PowerShell 支持、路径兼容性优化
- 🖥️ **终端渲染零闪烁** - 基于 Ink Static 组件的稳定渲染，抑制 resize 事件干扰
- 🌍 **中英双语支持** - 所有 CLI 输出根据 `ui_language` 设置自动切换中英文
- 📝 **全面 Markdown 渲染** - 直角边框表格、圆角卡片代码块、多色富文本、链接等
- 📂 **项目级配置友好** - 自动生成 skills、rules、mcp、plugins 目录，项目同名 skill 优先覆盖全局
- 🤖 **多 AI 提供商支持** - Anthropic Claude、OpenAI、GitHub Copilot、OpenAI Codex 及任意 OpenAI 兼容端点
- 🛠️ **丰富的工具集** - 36 内置工具 + MCP 动态工具扩展
- ⌨️ **52 个斜杠命令** - 覆盖会话管理、配置、项目操作、任务调度等
- 🧠 **多智能体协作** - 7 种内置专业 Agent，支持任务编排
- 🔌 **灵活扩展系统** - 插件、钩子、技能、MCP 服务器
- 🔐 **完善权限控制** - 三种模式 + 细粒度规则 + Always Allow 一键放行
- 💾 **记忆与上下文** - 项目知识持久化与动态检索
- 🎨 **现代终端界面** - React + Ink 组件化 TUI

### 界面展示

<div align="center">
  <p>欢迎界面 & 富文本渲染</p>
  <img src="docs/images/image1.png" alt="IllusionCode 欢迎界面" width="48%" />
  <img src="docs/images/image2.png" alt="IllusionCode 富文本渲染" width="48%" />
</div>

<div align="center">
  <p>演示视频</p>
  <video controls width="720">
    <source src="docs/videos/demonstration.mp4" type="video/mp4" />
  </video>
  <p>视频链接（回退）：<a href="docs/videos/demonstration.mp4">docs/videos/demonstration.mp4</a></p>
</div>

### 设计来源与创新

**继承自 Claude Code**：完整注入 Claude Code 的系统提示词、工具定义、权限模型和多智能体协调架构，确保行为一致性。

**灵感源自 OpenHarness**：Python 架构层面的设计参考了 OpenHarness 的理念。

**Cron 架构对齐 OpenClaw**：定时任务系统采用与 OpenClaw 相同的调度器架构，支持独立会话执行、执行历史记录和连续错误追踪。

**cc-switch 代理路由**：通过 cc-switch 反代工具实现本地代理路由，支持将请求转发到不同的 AI 提供商。

**Windows 深度优化**：自动查找 Git 安装路径，PowerShell 与 Bash 工具统一处理，路径分隔符自动兼容，Windows 用户开箱即用。

**终端零闪烁**：采用 Ink `<Static>` 组件架构，已完成消息静态渲染，流式消息动态渲染，彻底解决终端闪烁问题。

**中英双语界面**：所有 CLI 输出（auth、mcp、plugin、cron、session 等）均通过 i18n 系统根据 `ui_language` 字段自动切换语言，首次运行时可选择语言偏好。

**全面 Markdown 渲染**：终端内完整渲染直角边框表格、圆角卡片式代码块、多色富文本（加粗、斜体、行内代码、链接等），AI 回复可读性大幅提升。

**项目级配置自动化**：自动生成 `<project>/.illusion/rules/` 和 `<project>/.illusion/skills/` 目录，项目级配置优先于全局配置，便于团队协作。

---

## 🚀 快速开始

### 环境要求

- Python >= 3.10
- Node.js (用于前端 TUI)
- 支持 Windows、macOS、Linux
- Windows 用户：自动查找 Git，无需手动配置 PATH

### 安装

```bash
git clone https://github.com/your-repo/illusion-code.git
cd illusion-code
uv sync
```

> **注意**：`uv sync` 仅在项目目录下创建虚拟环境，不会将 `illusion` 命令注册到系统 PATH。若需在任意目录使用 `illusion` 命令，有以下方式：
>
> ```bash
> # 方式一：在项目目录下使用 uv run
> cd illusion-code
> uv run illusion
>
> # 方式二：激活虚拟环境后使用
> # Windows
> .venv\Scripts\activate
> # macOS / Linux
> source .venv/bin/activate
> illusion
>
> # 方式三：使用 pip 全局安装
> pip install -e .
> ```

### 基本使用

> **首次使用建议**：先执行 `uv run illusion auth login` 配置 API 认证，否则可能因未登录或模型不可用而报错退出。

```bash
# 首次使用：配置认证
uv run illusion auth login

# 启动交互式会话（推荐）
illusion

# 非交互式打印模式
illusion -p "帮我分析这个项目的结构"

# 指定模型
illusion -m env_1.model_2

# 继续最近会话
illusion --continue

# 恢复指定会话
illusion --resume <session-id>

# 设置权限模式
illusion --permission-mode full_auto

# 指定 API 格式
illusion --api-format openai
```

---

## 📚 命令系统

### 子命令

```bash
# 认证管理
illusion auth login              # 交互式配置提供商（自定义/Anthropic/OpenAI/Copilot/Codex）
illusion auth status             # 查看所有环境的认证状态
illusion auth logout [env_N]     # 清除环境凭据
illusion auth switch [env_N]     # 切换活动环境
illusion auth add-model <env_N> <model_name>  # 向已有环境添加模型

# MCP 管理
illusion mcp list                # 列出 MCP 服务器
illusion mcp add <name> <config> # 添加服务器
illusion mcp remove <name>       # 移除服务器

# 插件管理
illusion plugin list             # 列出插件
illusion plugin install <source> # 安装插件
illusion plugin uninstall <name> # 卸载插件

# 定时任务
illusion cron start              # 启动调度器
illusion cron stop               # 停止调度器
illusion cron status             # 查看状态
illusion cron list               # 列出任务
illusion cron toggle <name> <true|false>  # 启用/禁用任务
illusion cron run <name>         # 手动触发执行任务
illusion cron history            # 查看执行历史
illusion cron logs               # 查看调度器日志
```

### 交互式斜杠命令

在交互式会话中，可使用以下命令：

| 类别 | 命令示例 | 说明 |
|------|----------|------|
| 会话管理 | `/help`, `/clear`, `/exit`, `/rewind`, `/delete` | 管理会话状态 |
| 记忆快照 | `/memory`, `/resume`, `/export`, `/rules` | 记忆与会话管理 |
| 配置设置 | `/config`, `/model`, `/permissions`, `/plan`, `/thinking` | 调整运行配置 |
| 插件扩展 | `/skills`, `/hooks`, `/mcp`, `/plugin` | 管理扩展功能 |
| 项目 Git | `/init`, `/diff`, `/branch`, `/commit` | 项目与版本控制 |
| 多智能体 | `/agents`, `/tasks`, `/continue` | Agent 协作 |

---

## 🏗️ 项目架构

```
illusion-code/
├── src/illusion/           # 主要源代码
│   ├── api/                # API 客户端 (Anthropic, OpenAI 等)
│   ├── auth/               # 认证管理
│   ├── commands/           # 斜杠命令系统 (52 个命令)
│   ├── config/             # 配置系统
│   ├── coordinator/        # 多智能体协调器
│   ├── engine/             # 核心对话引擎
│   ├── hooks/              # 钩子系统
│   ├── mcp/                # MCP 客户端
│   ├── memory/             # 记忆系统
│   ├── permissions/        # 权限系统
│   ├── plugins/            # 插件系统
│   ├── prompts/            # 提示词系统
│   ├── skills/             # 技能系统
│   ├── tasks/              # 任务管理
│   ├── tools/              # 工具集 (36 个工具)
│   ├── ui/                 # 用户界面
│   └── cli.py              # CLI 入口
├── frontend/terminal/      # React TUI 前端
├── tests/                  # 测试套件
└── pyproject.toml          # 项目配置
```

---

## 🔧 核心模块

### API 客户端层

支持多种 AI 提供商：

| 提供商 | API 格式 | 认证方式 |
|--------|----------|----------|
| Anthropic Claude | anthropic | API Key |
| OpenAI / 兼容接口 | openai | API Key |
| GitHub Copilot | openai | OAuth 设备码 |
| OpenAI Codex | openai | 外部 CLI (Codex CLI) |
| 自定义提供商 | anthropic / openai | API Key |

### 工具系统

提供 36 个核心工具，涵盖：

- **文件操作**: `file_read`, `file_write`, `file_edit`, `notebook_edit`
- **命令执行**: `bash`, `powershell`, `repl`
- **搜索**: `glob`, `grep`, `web_fetch`, `web_search`, `tool_search`
- **任务管理**: `task_create`, `task_get`, `task_list`, `task_update`, `task_output`, `task_stop`
- **Agent 协作**: `agent`, `send_message`, `team_create`, `team_delete`
- **模式切换**: `enter_plan_mode`, `exit_plan_mode`
- **会话控制**: `enter_worktree`, `exit_worktree`, `todo_write`, `sleep`, `brief`
- **配置与调试**: `config`, `lsp`, `mcp_auth`, `skill`, `structured_output`
- **交互**: `ask_user_question`
- **定时任务**: `cron`（统一工具，支持 status/list/add/update/remove/run 操作）

### 权限系统

三种权限模式：

| 模式 | 说明 |
|------|------|
| `default` | 修改类工具需要用户确认 |
| `plan` | 阻止所有修改类工具 |
| `full_auto` | 允许一切操作 |

### 多智能体协调器

内置 7 种专业 Agent：

| Agent | 用途 |
|-------|------|
| `general-purpose` | 通用研究和多步任务 |
| `Explore` | 文件搜索和代码探索专家 |
| `Plan` | 架构设计和实施规划专家 |
| `verification` | 对抗性验证专家 |
| `worker` | 实现导向的 Worker |
| `statusline-setup` | Shell PS1 转换器 |
| `illusion-guide` | Illusion Code / SDK / API 文档专家 |

---

## 🎨 前端技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18.3.1 | UI 框架 |
| Ink | 5.1.0 | 终端 UI 组件库 |
| TypeScript | 5.7.3 | 类型安全 |

---

## 📦 主要依赖

| 依赖 | 用途 |
|------|------|
| anthropic | Anthropic SDK |
| openai | OpenAI SDK |
| rich | 富文本输出 |
| prompt-toolkit | 高级输入处理 |
| textual | TUI 框架 |
| typer | CLI 框架 |
| pydantic | 数据验证 |
| httpx | HTTP 客户端 |
| mcp | MCP 协议 |

---

## ⚙️ 配置文件

### 配置文件概览

| 文件 | 位置 | 作用域 | 用途 |
|------|------|--------|------|
| `settings.json` | `~/.illusion/settings.json` | 全局 | 主设置文件，API配置、权限、钩子等 |
| `credentials.json` | `~/.illusion/credentials.json` | 全局 | 安全凭据存储（API密钥等） |
| `CLAUDE.md` | 项目根目录 | 项目级 | 项目指令和上下文 |
| `MEMORY.md` | 项目根目录 | 项目级 | 记忆入口文件 |
| `.illusion/mcp/*.json` | 项目根目录 | 项目级 | MCP 服务器配置 |
| `.illusion/rules/*.md` | 项目根目录 | 项目级 | 项目规则文件 |

#### 凭据文件 (credentials.json)

凭据文件位于 `~/.illusion/credentials.json`，用于安全存储 API 密钥。由 `illusion auth login` 命令自动管理，也可手动编辑。凭据按 `env_N` 分组存储，与 `settings.json` 中的环境配置对应。

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

**字段说明：**
- 顶级键为环境标识符（env_1, env_2 等），与 settings.json 中的 env_N 对应
- 每个环境下存储 `api_key` 等凭据
- 文件权限自动设置为 600（见下方说明）

**API 密钥存储方式**：API 密钥有两种存储方式，可根据需求选择：

| 方式 | 配置位置 | 优势 | 劣势 |
|------|----------|------|------|
| **安全模式** | `credentials.json`（由 `illusion auth login` 自动管理） | 密钥与配置分离，便于管理，文件权限受保护 | 需要额外文件 |
| **便捷模式** | `settings.json` 的 `env_N.api_key` 字段 | 配置集中在一个文件，简单直观 | 密钥明文存储，共享配置时需注意脱敏 |

两种方式可混用，运行时读取优先级：`env_N.api_key` > 环境变量 > `credentials.json`。

> **文件权限 600 说明**：`600` 是 Unix/Linux 文件权限码，表示「仅文件所有者可读写，其他用户无任何访问权限」。用数字表示为 `rw-------`，其中 `6`（读+写）对应所有者，`0` 对应同组用户，`0` 对应其他用户。在 Windows 系统上，此设置会被静默跳过（Windows 使用 ACL 权限模型，行为不同）。此限制保护 API 密钥不被同一系统上的其他用户读取。

### 配置优先级

配置解析优先级（从高到低）：

1. **CLI 参数** - 命令行传入的参数优先级最高
2. **环境变量** - 如 `ANTHROPIC_API_KEY`、`ANTHROPIC_MODEL` 等
3. **配置文件** - `~/.illusion/settings.json`
4. **默认值** - 代码内置的默认配置

---

### 全局配置 (settings.json)

全局配置文件位于 `~/.illusion/settings.json`，对所有项目生效。

#### 配置方式

settings.json 使用 `env_N` 分组格式管理多个环境/提供商配置。每个 `env_N` 是一个独立的环境配置（EnvConfig），包含 API 格式、端点、密钥和模型列表。通过 `model` 字段引用 `env_N.model_N` 来选择当前活跃模型。

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

> **提示**：`model` 字段格式为 `env_N.model_N`，用于指定当前使用哪个环境的哪个模型。可通过 `/model` 命令交互式切换。API 密钥可直接填在 `env_N.api_key` 中，也可通过 `illusion auth login` 存储到 credentials.json（更安全）。

#### 完整配置结构

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
  "ui_language": "zh-CN",
  "output_style": "default",
  "fast_mode": false,
  "effort": "medium",
  "passes": 1,
  "verbose": false
}
```

#### 配置字段说明

| 字段 | 类型 | 默认值 | 说明 | 示例 |
|------|------|--------|------|------|
| `env_N` | object | - | 环境配置组（EnvConfig），支持动态添加 env_1, env_2... | 见下方 EnvConfig 字段说明 |
| `model` | string | "env_1.model_1" | 当前活跃模型引用，格式为 `env_N.model_N` | `"env_2.model_1"` |
| `context_window` | int | 200000 | 上下文窗口大小 | `128000` |
| `system_prompt` | string\|null | null | 自定义系统提示词（全局覆盖） | `"你是一个专业的Python开发者"` |
| `max_tokens` | int | 16384 | 最大输出 token 数 | `32768` |
| `max_turns` | int | 200 | 最大对话轮数 | `500` |
| `ui_language` | string | "zh-CN" | 界面语言 | `"en-US"` |
| `fast_mode` | bool | false | 快速模式 | `true` |
| `effort` | string | "medium" | 推理强度级别：low/medium/high | `"high"` |
| `passes` | int | 1 | 推理轮数（1-8），控制 AI 对同一问题的迭代推理次数，值越大推理越深入但耗时越长 | `2` |
| `verbose` | bool | false | 详细输出模式 | `true` |

---

### 环境配置 (EnvConfig)

IllusionCode 支持通过 `env_N` 分组管理多个环境/提供商配置。每个环境配置（EnvConfig）对应一个独立的 API 提供商设置。

#### EnvConfig 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `api_format` | string | 是 | API 格式：anthropic / openai |
| `base_url` | string\|null | 否 | 自定义 API 端点，null 表示使用默认端点 |
| `api_key` | string | 否 | API 密钥（可直接填写，也可留空由 `illusion auth login` 存储到 credentials.json） |
| `system_prompt` | string\|null | 否 | 该环境的系统提示词（覆盖全局） |
| `model_N` | string | 否 | 模型名称，支持多个 model_1, model_2, model_3... |

#### 多模型配置示例

在同一个环境下配置多个模型，通过 `env_N.model_N` 引用切换：

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

**切换模型的方式**：

```bash
# 方式一：使用 /model 命令交互式切换
/model

# 方式二：使用 -m 参数指定模型
illusion -m env_1.model_2

# 方式三：修改 settings.json 中的 model 字段
# 将 "model" 改为 "env_1.model_2"
```

---

### 各提供商配置示例

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

> API 密钥可直接填在 `env_N.api_key` 中，也可通过 `illusion auth login` 存储到 credentials.json（更安全）。

**认证方式**：
- 交互式配置：`illusion auth login` → 选择 Anthropic
- 环境变量：`ANTHROPIC_API_KEY`

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

> API 密钥可直接填在 `env_N.api_key` 中，也可通过 `illusion auth login` 存储到 credentials.json（更安全）。

**认证方式**：
- 交互式配置：`illusion auth login` → 选择 OpenAI
- 环境变量：`OPENAI_API_KEY`

---

#### 3. 自定义提供商

`illusion auth login` 选择"自定义提供商"后，依次输入：

1. API 格式（openai / anthropic）
2. API 端点
3. API 密钥
4. 模型名称

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
# 交互式配置
illusion auth login  # 选择 GitHub Copilot
```

在浏览器中完成 GitHub 授权后自动配置。认证数据存储在 `~/.illusion/copilot_auth.json`。

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

**认证方式**：GitHub OAuth 设备码流程（由 `illusion auth login` 自动完成）

**要求**：需要有效的 GitHub Copilot 订阅。

**支持的模型**：gpt-5.5、gpt-5.3-codex、claude-opus-4.6、gemini-3.1-pro-preview 等（取决于订阅计划）

---

#### 5. OpenAI Codex (ChatGPT 订阅)

```bash
# 先安装并认证 Codex CLI
codex auth login

# 然后在 IllusionCode 中配置
illusion auth login  # 选择 OpenAI Codex
```

Codex 模式使用 ChatGPT 订阅的认证，通过读取 Codex CLI 的凭据文件 (`~/.codex/auth.json`) 实现。

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

**认证方式**：外部 CLI 凭据绑定（需要先通过 Codex CLI 完成认证）

**要求**：需要安装 [Codex CLI](https://github.com/openai/codex) 并拥有 ChatGPT Plus/Pro/Team 订阅。

---

#### 6. 多提供商混合配置

通过 `illusion auth login` 配置多个环境，使用 `illusion auth switch` 或 `/model` 命令切换：

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

> API 密钥可直接填在 `env_N.api_key` 中，也可存储到 credentials.json（更安全，由 `illusion auth login` 管理）。Copilot/Codex 的认证由各自的 OAuth 流程管理，不需要手动填写 API 密钥。

**切换方式**：
```bash
# 交互式切换环境
illusion auth switch

# 直接指定环境
illusion auth switch env_2

# 使用 /model 命令交互式切换模型
/model

# 使用 -m 参数直接指定
illusion -m env_2.model_1
```

---

### 项目级配置

项目级配置仅对当前项目生效，放置在项目根目录。

#### CLAUDE.md - 项目指令

在项目根目录创建 `CLAUDE.md` 文件，为 AI 提供项目特定的上下文和指令：

```markdown
# 项目说明

这是一个 Python Web 项目，使用 FastAPI 框架。

## 代码规范

- 使用 Python 3.10+ 特性
- 遵循 PEP 8 代码风格
- 使用 type hints

## 目录结构

- src/api: API 路由
- src/models: 数据模型
- src/services: 业务逻辑

## 注意事项

- 不要修改 tests/ 目录下的文件
- 提交前运行 pytest
```

#### .illusion/rules/ - 规则文件（目录自动生成）

在 `.illusion/rules/` 目录下创建 `.md` 文件，每个文件是一条独立规则：

```
项目根目录/
├── .illusion/
│   └── rules/
│       ├── python-style.md
│       ├── git-workflow.md
│       └── testing.md
```

#### MCP 服务器配置

MCP 服务器支持三种配置方式，优先级从高到低：**插件 > 项目级 > 全局设置**

##### 1. 全局配置（settings.json）

在 `~/.illusion/settings.json` 的 `mcp_servers` 字段中配置，对所有项目生效。支持 `mcp_servers`（snake_case）和 `mcpServers`（camelCase）两种键名：

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

也可以通过命令行管理：
```bash
illusion mcp list                # 列出 MCP 服务器
illusion mcp add <name> <config> # 添加服务器
illusion mcp remove <name>       # 移除服务器
```

##### 2. 项目级配置（.illusion/mcp/）

在项目根目录的 `.illusion/mcp/` 目录下创建 `.json` 文件，仅对当前项目生效（目录自动生成）：

**方式一：单服务器配置（文件名作为服务器名）**

```json
// .illusion/mcp/solidworks.json
{
  "type": "stdio",
  "command": "python",
  "args": ["E:\\claudecode\\SolidWorks-MCP\\server.py"],
  "enabled": true
}
```

**方式二：多服务器配置（使用 mcpServers 键）**

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

##### 3. 插件配置

在插件目录中放置 `.mcp.json` 或 `mcp.json` 文件，随插件自动加载：

```
~/.illusion/plugins/my-plugin/
├── plugin.json      # 插件清单
├── .mcp.json        # MCP 配置（或 mcp.json）
└── ...
```

插件中的 MCP 服务器会以 `插件名:服务器名` 的格式注册，避免与其他配置冲突。

##### MCP 服务器配置类型

| 类型 | 字段 | 说明 |
|------|------|------|
| `stdio` | command, args, env, cwd, log_file, enabled | 通过标准输入输出通信 |
| `http` | url, headers, enabled | 通过 HTTP 协议通信 |
| `ws` | url, headers, enabled | 通过 WebSocket 协议通信 |

> **`enabled` 字段**：所有类型的 MCP 服务器均支持 `enabled` 字段（默认 `true`）。设置为 `false` 可禁用单个服务器而不删除其配置。项目级配置文件中的 `mcpServers` 和 `mcp_servers` 两种键名均可使用。

---

### 权限配置

#### 权限模式

| 模式 | 值 | 说明 |
|------|-----|------|
| 默认模式 | `default` | 修改类工具需要用户确认 |
| 计划模式 | `plan` | 阻止所有修改类工具 |
| 全自动模式 | `full_auto` | 允许一切操作 |

#### 权限配置示例

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

### 钩子配置

钩子允许在特定事件发生时执行自定义操作。

#### 支持的钩子类型

| 钩子事件 | 说明 |
|----------|------|
| `PRE_TOOL_USE` | 工具执行前 |
| `POST_TOOL_USE` | 工具执行后 |
| `USER_PROMPT_SUBMIT` | 用户提交提示词后 |

#### 钩子配置示例

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
        "prompt": "检查用户输入是否包含敏感信息",
        "block_on_failure": true
      }
    ]
  }
}
```

#### 钩子类型详解

| 类型 | 必填字段 | 可选字段 | 说明 |
|------|----------|----------|------|
| `command` | command | timeout_seconds, matcher, block_on_failure | 执行 Shell 命令 |
| `prompt` | prompt | model, timeout_seconds, matcher, block_on_failure | 使用 LLM 验证 |
| `http` | url | headers, timeout_seconds, matcher, block_on_failure | 发送 HTTP 请求 |
| `agent` | prompt | model, timeout_seconds, matcher, block_on_failure | 使用 Agent 验证 |

---

### 环境变量

支持的环境变量：

| 变量名 | 说明 |
|--------|------|
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 |
| `OPENAI_API_KEY` | OpenAI API 密钥 |
| `ANTHROPIC_MODEL` | 默认模型 |
| `ANTHROPIC_BASE_URL` | API 端点 |
| `ILLUSION_MAX_TOKENS` | 最大 token 数 |
| `ILLUSION_MAX_TURNS` | 最大对话轮数 |
| `ILLUSION_SANDBOX_ENABLED` | 是否启用沙箱 |
| `ILLUSION_CONFIG_DIR` | 配置目录路径 |
| `ILLUSION_DATA_DIR` | 数据目录路径 |
| `ILLUSION_LOGS_DIR` | 日志目录路径 |

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
| `enabled` | true | 是否启用记忆功能 |
| `max_files` | 5 | 最大记忆文件数 |
| `max_entrypoint_lines` | 200 | 入口文件最大行数 |

---

### 沙箱配置

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

## 🔌 扩展开发

### 钩子系统

支持多种钩子类型：

- `PRE_TOOL_USE` - 工具执行前
- `POST_TOOL_USE` - 工具执行后
- `USER_PROMPT_SUBMIT` - 用户提交提示词后

### 插件系统

通过 `plugin.json` 清单定义：

- 技能 (Skills)
- 命令 (Commands)
- 钩子 (Hooks)
- MCP 服务器

---

## 🧪 开发与测试

```bash
# 安装开发依赖
uv sync --dev

# 运行测试
pytest

```

---

## 📄 许可证

本项目采用 [MIT](LICENSE) 许可证开源。

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

</div>
