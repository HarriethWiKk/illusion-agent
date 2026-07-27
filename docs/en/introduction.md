# Introduction

<div align="center">

**AI-Powered Command-Line Programming Assistant**

*The best of many worlds, unified into one intelligent coding tool*

</div>

---

IllusionCode is an open-source AI-powered command-line programming assistant that brings together the best ideas from many projects and adds its own innovations. It inherits Claude Code's complete prompt system and tool architecture, draws inspiration from OpenHarness's Python architecture design, uses the same Cron task scheduling architecture as OpenClaw, ports core infrastructure modules (async queue, stderr fd-level redirect, cross-platform SIGINT handler) from kimi-cli, references channel connection/rendering patterns (Feishu WS, WeChat iLink, QQ Bot gateway) from hermes-agent, and implements flexible proxy routing through cc-switch. On this foundation, IllusionCode provides deep Windows optimization, full bilingual (Chinese/English) interface support, more comprehensive Markdown terminal rendering than comparable projects, and a browser-based Web UI for a modern chat experience.

## Core Features

- 🌐 **Web UI Interface** - Browser-based chat interface with `illusion web`, featuring warm color design, session management, and real-time streaming (supplementary to the recommended terminal interface)
- 🪟 **Deep Windows Optimization** - Auto-detect Git, PowerShell support, path compatibility optimization
- 🖥️ **Zero Terminal Flicker** - Stable rendering based on Ink Static component, suppressing resize event interference
- 🌍 **Bilingual Interface** - All CLI output automatically switches between Chinese and English based on `ui_language` setting
- 📝 **Comprehensive Markdown Rendering** - Box-drawing tables, rounded card-style code blocks, multi-color rich text, links and more
- 📂 **Project-Level Config Friendly** - Auto-generate skills, rules, mcp, plugins directories, project-level skills override global ones
- 🤖 **Multi AI Provider Support** - Anthropic Claude, OpenAI, GitHub Copilot, OpenAI Codex, and any OpenAI-compatible endpoint
- 🛠️ **Rich Toolset** - 42 built-in tools (29 base + 13 channel) + MCP dynamic tool extension
- ⌨️ **49 Slash Commands** - Covering session management, configuration, project operations, task scheduling, etc.
- 🧠 **Multi-Agent Collaboration** - 7 built-in specialized Agents, supporting task orchestration
- 🔌 **Flexible Extension System** - Plugins, hooks, skills, MCP servers
- 🔐 **Comprehensive Permission Control** - Three modes + fine-grained rules + Always Allow one-click approval
- 💾 **Memory & Context** - Project knowledge persistence and dynamic retrieval
- 🎨 **Dual Interface** - Modern React + Ink terminal TUI + browser-based Web UI
- 🎯 **Reasoning Effort Control** - Supports low/medium/high/xhigh/max five reasoning effort levels with automatic fallback

## Interface Preview

<div align="center">
  <p>Welcome screen & rich text rendering</p>
  <img src="../images/image1.png" alt="IllusionCode welcome screen" width="48%" />
  <img src="../images/image2.png" alt="IllusionCode rich text rendering" width="48%" />
</div>

<div align="center">
  <p>Demo video</p>
  <a href="https://www.youtube.com/watch?v=ExrzKVjWPls">
    <img src="../images/IllusionCode.png" alt="Click to watch demo video" width="720" />
  </a>
  <p><a href="https://www.youtube.com/watch?v=ExrzKVjWPls">📺 Watch demo on YouTube</a></p>
</div>

## Design Origins & Innovations

**Inherited from Claude Code**: Complete injection of Claude Code's system prompts, tool definitions, permission model, and multi-agent coordination architecture, ensuring behavioral consistency.

**Inspired by OpenHarness**: Python architecture design references OpenHarness's ideas.

**Cron Architecture Aligned with OpenClaw**: The scheduled task system uses the same scheduler architecture as OpenClaw, supporting independent session execution, execution history tracking, and consecutive error monitoring.

**cc-switch Proxy Routing**: Local proxy routing through the cc-switch reverse proxy tool, supporting request forwarding to different AI providers.

**Infrastructure Ported from kimi-cli**: Core infrastructure modules including async queue (aioqueue, Queue + shutdown sentinel, Python < 3.13 polyfill), stderr fd-level redirect (stderr_redirect, StderrRedirector), and cross-platform SIGINT handler (signals) are ported from the kimi-cli project, with only docstring and logging adaptations.

**Channel Implementation Inspired by hermes-agent**: The connection/reconnection/rendering patterns of channel modules — Feishu WS long connection and message rendering strategy, WeChat iLink API client, and QQ Bot WS gateway — are referenced from the hermes-agent project.

**Deep Windows Optimization**: Auto-detect Git installation path, unified PowerShell and Bash tool processing, automatic path separator compatibility, out-of-the-box experience for Windows users.

**Zero Terminal Flicker**: Uses Ink `<Static>` component architecture, static rendering for completed messages, dynamic rendering for streaming messages, completely solving terminal flicker issues.

**Bilingual Interface**: All CLI output (auth, mcp, plugin, cron, session, etc.) automatically switches language via the i18n system based on the `ui_language` field. Language preference can be selected on first run.

**Comprehensive Markdown Rendering**: Full rendering of box-drawing tables, rounded card-style code blocks, multi-color rich text (bold, italic, inline code, links), significantly improving AI response readability.

**Project-Level Config Automation**: Auto-generate `<project>/.illusion/rules/` and `<project>/.illusion/skills/` directories, project-level configuration takes precedence over global configuration, facilitating team collaboration.

**Web UI Interface**: Browser-based chat interface powered by React + Vite + Tailwind CSS frontend and FastAPI + WebSocket backend. Features warm color design, session management, sidebar navigation, real-time streaming responses, right panel with context usage display, and full i18n support. Launch with `illusion web`. Note: The terminal interface is recommended as the primary mode for full feature support and better performance; the Web UI is intended as a supplementary option for scenarios where a terminal is unavailable.
