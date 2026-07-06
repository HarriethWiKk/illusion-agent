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

- 🌐 **Web UI Interface** - Browser-based chat interface with `illusion web`
- 🪟 **Deep Windows Optimization** - Auto-detect Git, PowerShell support
- 🖥️ **Zero Terminal Flicker** - Stable rendering based on Ink Static component
- 🌍 **Bilingual Interface** - Chinese/English auto-switch via `ui_language` setting
- 📝 **Comprehensive Markdown Rendering** - Tables, code blocks, rich text
- 🤖 **Multi AI Provider Support** - Anthropic, OpenAI, Copilot, Codex, and any compatible endpoint
- 🛠️ **Rich Toolset** - 34 built-in tools + MCP dynamic tool extension
- ⌨️ **47 Slash Commands** - Session, config, project, scheduling
- 🧠 **Multi-Agent Collaboration** - 7 built-in specialized Agents
- 🔌 **Flexible Extension System** - Plugins, hooks, skills, MCP servers
- 🔐 **Comprehensive Permission Control** - Three modes + fine-grained rules
- 🎯 **Reasoning Effort Control** - low/medium/high/xhigh/max levels

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

---

## 🚀 Quick Start

### Requirements

- Python >= 3.10
- Supports Windows, macOS, Linux
- Node.js 18+（仅源码安装需要，`pip install illusion-code` 无需 Node.js）

### Installation

```bash
# Recommended: pip install from PyPI（无需 Node.js）
pip install illusion-code

# Alternative: from source（需要 Node.js 18+）
git clone https://github.com/YunTaiHua/illusion-code.git
cd illusion-code
pip install .
```

### Basic Usage

```bash
# First-time: configure authentication
illusion auth login

# Start interactive session (recommended)
illusion

# Launch Web UI in browser
illusion web

# Non-interactive print mode
illusion -p "Analyze the structure of this project"

# Specify model
illusion -m env_1.model_2
```

---

## 📚 Detailed Documentation

| Topic | English | 中文 |
|-------|---------|------|
| Introduction | [docs/en/introduction.md](docs/en/introduction.md) | [docs/zh-CN/introduction.md](docs/zh-CN/introduction.md) |
| Getting Started | [docs/en/getting-started.md](docs/en/getting-started.md) | [docs/zh-CN/getting-started.md](docs/zh-CN/getting-started.md) |
| Commands | [docs/en/commands.md](docs/en/commands.md) | [docs/zh-CN/commands.md](docs/zh-CN/commands.md) |
| Settings & Credentials | [docs/en/settings.md](docs/en/settings.md) | [docs/zh-CN/settings.md](docs/zh-CN/settings.md) |
| Project Files & Memory | [docs/en/project-files.md](docs/en/project-files.md) | [docs/zh-CN/project-files.md](docs/zh-CN/project-files.md) |
| Extensions (MCP, Plugins, Skills, Hooks) | [docs/en/extensions.md](docs/en/extensions.md) | [docs/zh-CN/extensions.md](docs/zh-CN/extensions.md) |
| Architecture | [docs/en/architecture.md](docs/en/architecture.md) | [docs/zh-CN/architecture.md](docs/zh-CN/architecture.md) |
| Messaging Channels | [docs/en/channels.md](docs/en/channels.md) | [docs/zh-CN/channels.md](docs/zh-CN/channels.md) |

---

## 📄 License

This project is open-sourced under the [MIT](LICENSE) license.

---

## 🤝 Contributing

Welcome to submit Issues and Pull Requests!

---

</div>
