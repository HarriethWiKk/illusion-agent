"""
国际化消息模块
==============

本模块提供 CLI 输出的国际化（i18n）支持。
根据 settings.json 中的 ui_language 字段返回对应语言的文本。

使用示例：
    >>> from illusion.config.i18n import t
    >>> print(t("mcp_none"))
"""

from __future__ import annotations

import re
from typing import Any

# i18n 消息表
MESSAGES: dict[str, dict[str, str]] = {
    # --- auth ---
    "select_provider": {"zh-CN": "选择提供商:", "en-US": "Select a provider:"},
    "custom_provider": {"zh-CN": "自定义提供商", "en-US": "Custom provider"},
    "anthropic_label": {"zh-CN": "Anthropic (Claude API)", "en-US": "Anthropic (Claude API)"},
    "openai_label": {"zh-CN": "OpenAI / 兼容接口", "en-US": "OpenAI / compatible"},
    "copilot_label": {"zh-CN": "GitHub Copilot", "en-US": "GitHub Copilot"},
    "copilot_open_url": {"zh-CN": "请在浏览器中打开以下 URL 完成授权:", "en-US": "Open the following URL in your browser to authorize:"},
    "copilot_enter_code": {"zh-CN": "并输入代码: {code}", "en-US": "and enter code: {code}"},
    "copilot_waiting": {"zh-CN": "等待 GitHub 授权中...", "en-US": "Waiting for GitHub authorization..."},
    "copilot_auth_success": {"zh-CN": "GitHub Copilot 授权成功 (用户: {user})", "en-US": "GitHub Copilot authorized (user: {user})"},
    "copilot_no_subscription": {"zh-CN": "未订阅 GitHub Copilot，请先在 GitHub 上订阅", "en-US": "No GitHub Copilot subscription found, please subscribe on GitHub first"},
    "copilot_not_authenticated": {"zh-CN": "未认证 GitHub Copilot，请先运行 'illusion auth login'", "en-US": "GitHub Copilot not authenticated, run 'illusion auth login' first"},
    "copilot_device_expired": {"zh-CN": "设备码已过期，请重新运行登录", "en-US": "Device code expired, please retry login"},
    "copilot_auth_denied": {"zh-CN": "授权被拒绝", "en-US": "Authorization denied"},
    "codex_label": {"zh-CN": "OpenAI Codex (ChatGPT 订阅)", "en-US": "OpenAI Codex (ChatGPT subscription)"},
    "codex_not_found": {"zh-CN": "未找到 Codex CLI 认证，请先安装 Codex CLI 并运行 'codex auth login'", "en-US": "Codex CLI auth not found, please install Codex CLI and run 'codex auth login' first"},
    "codex_auth_success": {"zh-CN": "Codex 认证读取成功 (用户: {user})", "en-US": "Codex auth loaded successfully (user: {user})"},
    "codex_open_url": {"zh-CN": "请在浏览器中打开以下 URL 完成授权:", "en-US": "Open the following URL in your browser to authorize:"},
    "codex_enter_code": {"zh-CN": "并输入代码: {code}", "en-US": "and enter code: {code}"},
    "codex_waiting": {"zh-CN": "等待 ChatGPT 授权中...", "en-US": "Waiting for ChatGPT authorization..."},
    "codex_oauth_success": {"zh-CN": "Codex OAuth 授权成功 (用户: {user})", "en-US": "Codex OAuth authorized (user: {user})"},
    "codex_device_expired": {"zh-CN": "设备码已过期，请重新运行登录", "en-US": "Device code expired, please retry login"},
    "codex_auth_denied": {"zh-CN": "授权被拒绝", "en-US": "Authorization denied"},
    "codex_no_subscription": {"zh-CN": "未订阅 ChatGPT Plus/Pro，请先在 OpenAI 上订阅", "en-US": "No ChatGPT Plus/Pro subscription found, please subscribe on OpenAI first"},
    "codex_not_authenticated": {"zh-CN": "未认证 Codex，请先运行 'illusion auth login'", "en-US": "Codex not authenticated, run 'illusion auth login' first"},
    "enter_number": {"zh-CN": "输入序号", "en-US": "Enter number"},
    "invalid_selection": {"zh-CN": "无效选择", "en-US": "Invalid selection"},
    "select_api_format": {"zh-CN": "选择 API 格式:", "en-US": "Select API format:"},
    "enter_endpoint": {"zh-CN": "输入 API 端点", "en-US": "Enter API endpoint"},
    "enter_api_key": {"zh-CN": "输入 API 密钥", "en-US": "Enter API key"},
    "enter_model": {"zh-CN": "输入模型名称", "en-US": "Enter model name"},
    "model_required": {"zh-CN": "模型名称不能为空", "en-US": "Model name cannot be empty"},
    "endpoint_required": {"zh-CN": "端点不能为空", "en-US": "Endpoint cannot be empty"},
    "api_key_required": {"zh-CN": "API 密钥不能为空", "en-US": "API key cannot be empty"},
    "env_saved": {"zh-CN": "环境 {env_key} 已保存并激活", "en-US": "Environment {env_key} saved and activated"},
    "no_envs": {"zh-CN": "未配置任何环境，请先运行 'illusion auth login'", "en-US": "No environments configured, run 'illusion auth login' first"},
    "env_status_title": {"zh-CN": "环境认证状态:", "en-US": "Environment credential status:"},
    "col_env": {"zh-CN": "环境", "en-US": "Env"},
    "col_format": {"zh-CN": "格式", "en-US": "Format"},
    "col_model": {"zh-CN": "模型", "en-US": "Model"},
    "col_endpoint": {"zh-CN": "端点", "en-US": "Endpoint"},
    "col_credential": {"zh-CN": "凭据", "en-US": "Credential"},
    "configured": {"zh-CN": "已配置", "en-US": "configured"},
    "missing": {"zh-CN": "未配置", "en-US": "missing"},
    "active_mark": {"zh-CN": "← 当前", "en-US": "<-- active"},
    "select_env_to_logout": {"zh-CN": "选择要清除凭据的环境:", "en-US": "Select environment to clear credentials:"},
    "credential_cleared": {"zh-CN": "已清除环境 {env_key} 的凭据", "en-US": "Credentials cleared for {env_key}"},
    "select_env_to_switch": {"zh-CN": "选择要切换的环境:", "en-US": "Select environment to switch to:"},
    "switched_to": {"zh-CN": "已切换到环境 {env_key}", "en-US": "Switched to environment {env_key}"},
    "env_not_found": {"zh-CN": "环境 {env_key} 不存在", "en-US": "Environment {env_key} not found"},
    "select_language": {"zh-CN": "选择界面语言:", "en-US": "Select interface language:"},
    "language_set": {"zh-CN": "界面语言已设置为: {lang}", "en-US": "Interface language set to: {lang}"},
    "skip_default": {"zh-CN": "回车跳过，使用默认值", "en-US": "Press Enter to skip, use default"},
    "model_added": {"zh-CN": "已向 {env_key} 添加模型 {model_key}: {model_name}", "en-US": "Added {model_key} to {env_key}: {model_name}"},
    # --- 后端事件 ---
    "task_stopped": {"zh-CN": "当前任务已停止。", "en-US": "Current task stopped."},
    "no_active_task": {"zh-CN": "没有正在执行的任务", "en-US": "No active task to stop"},
    "bg_agent_waiting": {"zh-CN": "等待后台代理完成", "en-US": "Waiting for background agent"},
    "bg_agent_resuming": {"zh-CN": "后台代理已完成，继续执行", "en-US": "Background agent completed, resuming"},
    "default_endpoint": {"zh-CN": "默认", "en-US": "default"},
    # --- mcp ---
    "mcp_none": {"zh-CN": "未配置 MCP 服务器", "en-US": "No MCP servers configured"},
    "mcp_invalid_json": {"zh-CN": "无效 JSON: {exc}", "en-US": "Invalid JSON: {exc}"},
    "mcp_invalid_config": {"zh-CN": "无效的 MCP 服务器配置: {exc}", "en-US": "Invalid MCP server config: {exc}"},
    "mcp_added": {"zh-CN": "已添加 MCP 服务器: {name}", "en-US": "Added MCP server: {name}"},
    "mcp_not_found": {"zh-CN": "未找到 MCP 服务器: {name}", "en-US": "MCP server not found: {name}"},
    "mcp_removed": {"zh-CN": "已移除 MCP 服务器: {name}", "en-US": "Removed MCP server: {name}"},
    # --- plugin ---
    "plugin_none": {"zh-CN": "未安装插件", "en-US": "No plugins installed"},
    "plugin_enabled": {"zh-CN": "启用", "en-US": "enabled"},
    "plugin_disabled": {"zh-CN": "禁用", "en-US": "disabled"},
    "plugin_installed": {"zh-CN": "已安装插件: {name}", "en-US": "Installed plugin: {name}"},
    "plugin_uninstalled": {"zh-CN": "已卸载插件: {name}", "en-US": "Uninstalled plugin: {name}"},
    # --- cron ---
    "cron_already_running": {"zh-CN": "调度器已在运行", "en-US": "Cron scheduler is already running"},
    "cron_started": {"zh-CN": "调度器已启动 (pid={pid})", "en-US": "Cron scheduler started (pid={pid})"},
    "cron_stopped": {"zh-CN": "调度器已停止", "en-US": "Cron scheduler stopped"},
    "cron_not_running": {"zh-CN": "调度器未在运行", "en-US": "Cron scheduler is not running"},
    "cron_state_running": {"zh-CN": "运行中", "en-US": "running"},
    "cron_state_stopped": {"zh-CN": "已停止", "en-US": "stopped"},
    "cron_jobs_none": {"zh-CN": "未配置定时任务", "en-US": "No cron jobs configured"},
    "cron_recurring": {"zh-CN": "周期", "en-US": "recurring"},
    "cron_oneshot": {"zh-CN": "单次", "en-US": "one-shot"},
    "cron_never": {"zh-CN": "从未", "en-US": "never"},
    "cron_na": {"zh-CN": "无", "en-US": "n/a"},
    "cron_errors": {"zh-CN": "错误: {n}", "en-US": "errors: {n}"},
    "cron_prompt_label": {"zh-CN": "提示词", "en-US": "prompt"},
    "cron_last_label": {"zh-CN": "上次", "en-US": "last"},
    "cron_next_label": {"zh-CN": "下次", "en-US": "next"},
    "cron_job_not_found": {"zh-CN": "未找到定时任务: {name}", "en-US": "Cron job not found: {name}"},
    "cron_enabled": {"zh-CN": "已启用", "en-US": "enabled"},
    "cron_disabled": {"zh-CN": "已禁用", "en-US": "disabled"},
    "cron_job_state": {"zh-CN": "任务 '{name}' {state}", "en-US": "Job '{name}' {state}"},
    "cron_no_prompt": {"zh-CN": "任务无提示词: {name}", "en-US": "Job has no prompt: {name}"},
    "cron_running_job": {"zh-CN": "正在执行任务 '{name}'...", "en-US": "Running job '{name}'..."},
    "cron_finished": {"zh-CN": "完成: {status} (rc={rc})", "en-US": "Finished: {status} (rc={rc})"},
    "cron_output": {"zh-CN": "输出:", "en-US": "Output:"},
    "cron_error": {"zh-CN": "错误:", "en-US": "Error:"},
    "cron_no_history": {"zh-CN": "无执行历史", "en-US": "No execution history"},
    "cron_no_log": {"zh-CN": "未找到调度器日志，请先运行: illusion cron start", "en-US": "No scheduler log found. Start with: illusion cron start"},
    # --- session ---
    "session_not_found_prev": {"zh-CN": "未找到之前的会话", "en-US": "No previous session found"},
    "session_continuing": {"zh-CN": "继续会话: {summary}", "en-US": "Continuing session: {summary}"},
    "session_no_saved": {"zh-CN": "未找到保存的会话", "en-US": "No saved sessions found"},
    "session_saved_list": {"zh-CN": "已保存的会话:", "en-US": "Saved sessions:"},
    "session_msg_count": {"zh-CN": "{n} 条消息", "en-US": "{n} msgs"},
    "session_enter_id": {"zh-CN": "输入会话序号或 ID", "en-US": "Enter session number or ID"},
    "session_not_found": {"zh-CN": "未找到会话: {id}", "en-US": "Session not found: {id}"},
    "print_requires_prompt": {"zh-CN": "错误: -p/--print 需要提供提示词，例如 -p '你的提示词'", "en-US": "Error: -p/--print requires a prompt, e.g. -p 'your prompt'"},
    # --- settings ---
    "no_api_key": {"zh-CN": "未找到 API 密钥。请使用 'illusion auth login' 配置，或设置 ANTHROPIC_API_KEY / OPENAI_API_KEY 环境变量", "en-US": "No API key found. Run 'illusion auth login' or set ANTHROPIC_API_KEY / OPENAI_API_KEY environment variable"},
    "no_auth": {"zh-CN": "未找到认证信息。请使用 'illusion auth login' 配置，或设置对应的环境变量", "en-US": "No credentials found. Run 'illusion auth login' or set the matching environment variable"},
    # --- manager ---
    "unknown_env": {"zh-CN": "未知环境: {env_key}", "en-US": "Unknown environment: {env_key}"},
    "cannot_remove_active_env": {"zh-CN": "不能移除当前活动环境", "en-US": "Cannot remove the active environment"},
    # --- model ---
    "model_active": {"zh-CN": "当前模型：{model}", "en-US": "Active model: {model}"},
    "model_active_detail": {"zh-CN": "  模型：{name}\n  API 格式：{fmt}\n  基础 URL：{url}", "en-US": "  model: {name}\n  api_format: {fmt}\n  base_url: {url}"},
    "model_list_title": {"zh-CN": "模型列表：", "en-US": "Models:"},
    "model_set_to": {"zh-CN": "模型已设置为 {ref}：{name}", "en-US": "Model set to {ref}: {name}"},
    "model_unknown": {"zh-CN": "未知模型：{ref}。使用 /model list 查看可用模型。", "en-US": "Unknown model: {ref}. Use /model list to see available models."},
    "model_usage": {"zh-CN": "用法：/model [show|set MODEL]", "en-US": "Usage: /model [show|set MODEL]"},
    "model_env_model": {"zh-CN": "模型：{name}", "en-US": "model: {name}"},
    "model_api_format": {"zh-CN": "API 格式：{fmt}", "en-US": "api_format: {fmt}"},
    "model_base_url": {"zh-CN": "基础 URL：{url}", "en-US": "base_url: {url}"},
    "model_default_url": {"zh-CN": "（默认）", "en-US": "(default)"},
    # --- compact ---
    "compact_warning_approaching": {"zh-CN": "上下文使用量：~{pct}% — 接近自动压缩阈值", "en-US": "Context usage: ~{pct}% — approaching auto-compact threshold"},
    "compact_compacted": {"zh-CN": "已压缩上下文以释放空间", "en-US": "Context compacted to free up space"},
    "compact_overflow_detected": {"zh-CN": "检测到上下文溢出，尝试响应式压缩…", "en-US": "Context overflow detected, attempting reactive compact..."},
    "compact_reactive_success": {"zh-CN": "响应式压缩成功，正在重试请求…", "en-US": "Reactive compact succeeded, retrying request..."},
    "compact_overflow_failed": {"zh-CN": "上下文溢出且响应式压缩失败：{error}", "en-US": "Context overflow and reactive compact failed: {error}"},
    "compact_network_error": {"zh-CN": "网络错误：{error}。请检查网络连接后重试。", "en-US": "Network error: {error}. Check your internet connection and try again."},
    "compact_api_error": {"zh-CN": "API 错误：{error}", "en-US": "API error: {error}"},
    "compact_result": {"zh-CN": "已压缩对话：{before} → {after} 条消息（节省 ~{saved} tokens）。", "en-US": "Compacted conversation from {before} to {after} messages (saved ~{saved} tokens)."},
    "compact_summary_prefix": {"zh-CN": "本会话从之前超出上下文限制的对话继续。以下摘要涵盖对话的早期部分。", "en-US": "This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation."},
    "compact_recent_preserved": {"zh-CN": "最近的消息已原样保留。", "en-US": "Recent messages are preserved verbatim."},
    "compact_suppress_followup": {"zh-CN": "\n从上次中断处继续对话，不要向用户提问。直接继续 — 不要确认摘要，不要复述进展，不要以「我继续」等开头。像中断从未发生一样继续上次的任务。", "en-US": "\nContinue the conversation from where it left off without asking the user any further questions. Resume directly — do not acknowledge the summary, do not recap what was happening, do not preface with \"I'll continue\" or similar. Pick up the last task as if the break never happened."},
    "compact_conversation_start": {"zh-CN": "（对话开始）", "en-US": "(conversation start)"},
    "permission_denied_stopped": {"zh-CN": "权限被拒绝，已终止当前操作（{tool}）。", "en-US": "Permission denied, stopped current operation ({tool})."},
    # --- update ---
    "update_checking": {"zh-CN": "正在检查更新...", "en-US": "Checking for updates..."},
    "update_latest": {"zh-CN": "已是最新版本 {version}", "en-US": "Already up to date ({version})"},
    "update_available": {"zh-CN": "发现新版本: {current} → {latest}", "en-US": "Update available: {current} → {latest}"},
    "update_confirm": {"zh-CN": "按回车开始更新，Ctrl+C 取消", "en-US": "Press Enter to update, Ctrl+C to cancel"},
    "update_installing": {"zh-CN": "正在安装...", "en-US": "Installing..."},
    "update_success": {"zh-CN": "更新成功！新版本: {version}", "en-US": "Updated successfully! New version: {version}"},
    "update_failed": {"zh-CN": "更新失败: {error}", "en-US": "Update failed: {error}"},
    "update_network_error": {"zh-CN": "网络连接失败，请检查网络设置", "en-US": "Network error, please check your connection"},
    "update_deps_checking": {"zh-CN": "正在检查依赖更新...", "en-US": "Checking dependency updates..."},
    "update_deps_available": {"zh-CN": "以下依赖可升级:", "en-US": "The following dependencies can be upgraded:"},
    "update_deps_confirm": {"zh-CN": "按回车更新依赖，Ctrl+C 取消", "en-US": "Press Enter to update dependencies, Ctrl+C to cancel"},
    "update_deps_success": {"zh-CN": "依赖更新完成", "en-US": "Dependencies updated successfully"},
    # 计划审批
    "plan_approval": {"zh-CN": "计划审批", "en-US": "Plan approval"},
    "plan_approve_question": {"zh-CN": "是否批准此计划？", "en-US": "Do you approve this plan?"},
    "plan_approve": {"zh-CN": "批准", "en-US": "Approve"},
    "plan_reject": {"zh-CN": "拒绝", "en-US": "Reject"},
    "plan_start_impl": {"zh-CN": "开始执行", "en-US": "Start implementation"},
    "plan_return_mode": {"zh-CN": "返回计划模式", "en-US": "Return to plan mode"},
}

# --- 命令描述翻译 ---
COMMAND_DESCRIPTIONS_ZH: dict[str, str] = {
    "help": "显示可用命令及用法说明",
    "exit": "退出 IllusionCode",
    "clear": "清空当前对话并开启新会话",
    "new": "开启新对话并重置任务 ID",
    "version": "显示已安装版本",
    "status": "显示会话状态",
    "context": "显示上下文使用量或管理上下文窗口",
    "summary": "总结对话历史",
    "compact": "压缩较早对话历史",
    "memory": "查看和管理项目记忆",
    "hooks": "显示已配置 hooks",
    "resume": "恢复最近保存的会话",
    "export": "导出当前转录",
    "share": "创建可分享的转录快照",
    "copy": "复制最新回复或指定文本",
    "rewind": "移除最新对话轮次",
    "files": "列出当前工作区文件",
    "init": "初始化项目 IllusionCode 文件",
    "bridge": "查看 bridge 辅助信息并创建 bridge 会话",
    "login": "查看认证状态或保存 API Key",
    "logout": "清除已保存 API Key",
    "feedback": "保存 CLI 反馈到本地日志",
    "skills": "列出或显示可用技能",
    "config": "显示或更新配置",
    "mcp": "显示 MCP 状态",
    "plugin": "管理插件",
    "reload-plugins": "重新加载当前工作区插件发现结果",
    "permissions": "显示或更新权限模式",
    "plan": "切换计划权限模式",
    "thinking": "显示或更新思考模式",
    "fast": "显示或更新快速模式",
    "effort": "显示或更新推理强度",
    "passes": "显示或更新推理轮数",
    "turns": "显示或更新最大 agent 轮数",
    "continue": "在中断后继续上一轮工具循环",
    "model": "显示或更新默认模型",
    "language": "显示或更新界面语言",
    "output-style": "显示或更新输出风格",
    "doctor": "显示环境诊断信息",
    "diff": "显示 git diff 输出",
    "branch": "显示 git 分支信息",
    "commit": "显示状态或创建 git 提交",
    "issue": "显示或更新项目 issue 上下文",
    "pr_comments": "显示或更新项目 PR 评论上下文",
    "privacy-settings": "显示本地隐私与存储设置",
    "delete": "清理选定的会话",
    "rules": "查看选定的规则",
    "update": "检查并更新 IllusionCode",
}

# --- 斜杠命令输出翻译 ---

# 命令消息精确匹配表（英文 -> 中文）
_COMMAND_EXACT: dict[str, str] = {
    # 通用
    "Available commands:": "可用命令：",
    "(empty)": "（空）",
    "(no output)": "（无输出）",
    "(no directories)": "（无目录）",
    "(no matching files)": "（无匹配文件）",
    "(no diff)": "（无差异）",
    "(working tree clean)": "（工作区干净）",
    # 会话
    "Conversation cleared.": "对话已清空。",
    "Started a new conversation session.": "已开启新对话。",
    "No saved sessions found for this project.": "当前项目未找到已保存会话。",
    "Nothing to copy.": "没有可复制的内容。",
    "Deleted current session:": "已删除当前会话：",
    # 记忆与 hooks
    "No memory files.": "没有记忆文件。",
    "No hooks configured.": "未配置 hooks。",
    # 插件与技能
    "No plugins discovered.": "未发现插件。",
    "No skills available.": "没有可用技能。",
    # 项目初始化
    "Project already initialized for IllusionCode.": "项目已完成 IllusionCode 初始化。",
    "## Files created": "## 已创建文件",
    "## Files updated": "## 已更新文件",
    "## Project analysis": "## 项目分析",
    "## Next steps": "## 下一步建议",
    "- Review `CLAUDE.md` for project configuration": "- 查看 `CLAUDE.md` 了解项目配置",
    "- Review `ILLUSION.md` for project-specific guidance": "- 查看 `ILLUSION.md` 了解项目特定指导",
    "- Run `/memory` to manage project memories": "- 运行 `/memory` 管理项目记忆",
    "- Run `/skills` to view available skills": "- 运行 `/skills` 查看可用技能",
    "- Adjust `CLAUDE.md` as needed": "- 根据需要调整 `CLAUDE.md`",
    # Bridge
    "No bridge sessions.": "没有 bridge 会话。",
    # 认证
    "Stored API key in ~/.illusion/settings.json": "API Key 已保存到 ~/.illusion/settings.json",
    "Cleared stored API key.": "已清除已保存 API Key。",
    # 反馈
    "Usage: /feedback TEXT": "用法：/feedback 文本",
    # 计划模式
    "Plan mode enabled.": "计划模式已开启。",
    "Plan mode disabled.": "计划模式已关闭。",
    # 计划审批
    "Plan approved. Starting implementation.": "计划已批准，开始实施。",
    "User rejected the plan.": "用户拒绝了该计划。",
    # 模型
    "Usage: /model [show|set MODEL]": "用法：/model [show|set MODEL]",
    "Model set to": "模型已切换为",
    # 语言
    "Available UI languages: zh-CN, en": "可用界面语言：zh-CN, en",
    "Usage: /language [show|list|set zh-CN|set en]": "用法：/language [show|list|set zh-CN|set en]",
    # 输出风格
    "Usage: /output-style [show|list|set NAME]": "用法：/output-style [show|list|set NAME]",
    # 诊断与隐私
    "Doctor summary:": "诊断摘要：",
    "Privacy settings:": "隐私设置：",
    # Git
    "Usage: /branch [show|list]": "用法：/branch [show|list]",
    "Nothing to commit.": "没有可提交的改动。",
    "Progress must be an integer between 0 and 100.": "进度必须是 0 到 100 之间的整数。",
    "Nothing to continue (no pending tool results).": "没有待继续的内容（无待处理工具结果）。",
    "Continuing pending tool loop...": "正在继续待处理的工具循环…",
    # MCP
    "HTTP/WS MCP auth supports bearer or header modes.": "HTTP/WS MCP 认证支持 bearer 或 header 模式。",
    "stdio MCP auth supports bearer or env modes.": "stdio MCP 认证支持 bearer 或 env 模式。",
    "No MCP servers configured.": "未配置 MCP 服务器。",
    # Issue 与 PR 评论
    "Cleared issue context.": "已清除 issue 上下文。",
    "No issue context to clear.": "没有可清除的 issue 上下文。",
    "Cleared PR comments context.": "已清除 PR 评论上下文。",
    "No PR comments context to clear.": "没有可清除的 PR 评论上下文。",
    # 上下文窗口
    "Error: context window must be positive": "错误：上下文窗口必须为正数",
    "Error: invalid number": "错误：无效的数字",
    "Usage: /context [usage|window|set N]": "用法：/context [usage|window|set N]",
    # 用法提示
    "Usage: /summary [MAX_MESSAGES]": "用法：/summary [最大消息数]",
    "Usage: /compact [PRESERVE_RECENT]": "用法：/compact [保留近期消息数]",
    "Usage: /memory add TITLE :: CONTENT": "用法：/memory add 标题 :: 内容",
    "Usage: /memory [list|show NAME|add TITLE :: CONTENT|remove NAME]": "用法：/memory [list|show 名称|add 标题 :: 内容|remove 名称]",
    "Usage: /rewind [TURNS] [both|conversation|code]": "用法：/rewind [轮数] [both|conversation|code]",
    "Usage: /config [show|set KEY VALUE]": "用法：/config [show|set 键 值]",
    "Usage: /fast [show|on|off|toggle]": "用法：/fast [show|on|off|toggle]",
    "Usage: /thinking [show|on|off|toggle]": "用法：/thinking [show|on|off|toggle]",
    "Usage: /effort [show|low|medium|high|xhigh|max]": "用法：/effort [show|low|medium|high|xhigh|max]",
    "Usage: /passes [show|COUNT]": "用法：/passes [数量]",
    "Usage: /turns [show|COUNT]": "用法：/turns [数量]",
    "Usage: /continue [COUNT]": "用法：/continue [数量]",
    "Usage: /plan [on|off]": "用法：/plan [on|off]",
    "Usage: /permissions [show|set MODE]": "用法：/permissions [show|set 模式]",
    "Usage: /issue set TITLE :: BODY": "用法：/issue set 标题 :: 正文",
    "Usage: /issue [show|set TITLE :: BODY|clear]": "用法：/issue [show|set 标题 :: 正文|clear]",
    "Usage: /pr_comments add FILE[:LINE] :: COMMENT": "用法：/pr_comments add 文件[:行号] :: 评论",
    "Usage: /pr_comments [show|add FILE[:LINE] :: COMMENT|clear]": "用法：/pr_comments [show|add 文件[:行号] :: 评论|clear]",
    "Usage: /plugin [list|enable NAME|disable NAME|install PATH|uninstall NAME]":
        "用法：/plugin [list|enable 名称|disable 名称|install 路径|uninstall 名称]",
    "Usage: /bridge [show|encode API_BASE_URL TOKEN|decode SECRET|sdk API_BASE_URL SESSION_ID|spawn CMD|list|output SESSION_ID|stop SESSION_ID]":
        "用法：/bridge [show|encode API_BASE_URL TOKEN|decode SECRET|sdk API_BASE_URL SESSION_ID|spawn CMD|list|output SESSION_ID|stop SESSION_ID]",
    # 快速模式
    "No conversation content to summarize.": "没有可总结的对话内容。",
    # 删除与规则
    "Saved sessions:": "已保存会话：",
    "Use /resume <session_id> to restore a specific session.": "使用 /resume <会话ID> 恢复指定会话。",
    # 登录
    "Usage: /login API_KEY": "用法：/login API_KEY",
    # Doctor
    "- backend host: available": "- 后端宿主：可用",
    "- network: enabled only for provider and explicit web/MCP calls": "- 网络：仅用于提供商和显式 web/MCP 调用",
    "- storage: local files under ~/.illusion and project .illusion": "- 存储：本地文件位于 ~/.illusion 和项目 .illusion",
    # 沙箱
    "Sandbox status: enabled": "沙箱状态：已启用",
    "Sandbox status: disabled": "沙箱状态：已禁用",
    "Use /config set sandbox.enabled true to enable": "使用 /config set sandbox.enabled true 启用",
    "  Fail if unavailable: yes": "  失败时退出：是",
    "  Fail if unavailable: no": "  失败时退出：否",
    "  Auto-allow bash: yes": "  自动允许 bash：是",
    "  Auto-allow bash: no": "  自动允许 bash：否",
    "  Allow unsandboxed: yes": "  允许禁用沙箱：是",
    "  Allow unsandboxed: no": "  允许禁用沙箱：否",
    "  Enabled platforms: all": "  限制平台：无（全部平台）",
    "  Excluded commands: none": "  排除命令：无",
}

# 命令消息正则替换表（pattern, replacement）
# replacement 可以是字符串（含 \1 等反向引用）或 lambda(match) -> str
_COMMAND_SUBSTITUTIONS: list[tuple[str, str | Any]] = [
    # 版本
    (r"^IllusionCode (.+)$", r"IllusionCode 版本 \1"),
    # 上下文窗口
    (r"^Context window: (\d[\d,]*) tokens$", r"上下文窗口：\1 tokens"),
    (r"^Context window set to (\d[\d,]*) tokens$", r"上下文窗口已设置为 \1 tokens"),
    (r"^Context Window: (\d[\d,]*) tokens$", r"上下文窗口：\1 tokens"),
    (r"^Estimated Used: ~(\d[\d,]*) tokens \((\d+)%\)$", r"预估已用：~\1 tokens（\2%）"),
    (r"^Remaining: ~(\d[\d,]*) tokens$", r"剩余：~\1 tokens"),
    (r"^Actual API Usage: input=(\d[\d,]*) output=(\d[\d,]*)$", r"实际 API 用量：input=\1 output=\2"),
    # 模型
    (r"^Model: (.+)$", r"模型：\1"),
    (r"^Model set to (.+)\. Restart session to use it\.$", r"模型已设置为 \1。重启会话后生效。"),
    (r"^Model set to (.+)\.$", r"模型已设置为 \1。"),
    (r"^Unknown model: (.+)$", r"未知模型：\1"),
    # 语言
    (r"^UI language: (.+)$", r"界面语言：\1"),
    (r"^UI language set to (.+)$", r"界面语言已设置为 \1"),
    # 输出风格
    (r"^Output style: (.+)$", r"输出风格：\1"),
    (r"^Output style set to (.+)$", r"输出风格已设置为 \1"),
    (r"^Unknown output style: (.+)$", r"未知输出风格：\1"),
    # 快速模式
    (r"^Fast mode: (on|off)$", r"快速模式：\1"),
    (r"^Fast mode (enabled|disabled)\.$",
     lambda m: f"快速模式{'已开启' if m.group(1) == 'enabled' else '已关闭'}。"),
    # 思考模式
    (r"^Thinking mode: (on|off)$", r"思考模式：\1"),
    (r"^Thinking mode (enabled|disabled)\.$",
     lambda m: f"思考模式{'已开启' if m.group(1) == 'enabled' else '已关闭'}。"),
    # 推理强度
    (r"^Reasoning effort: (.+)$", r"推理强度：\1"),
    (r"^Reasoning effort set to (.+)\.$", r"推理强度已设置为 \1。"),
    # 推理轮数
    (r"^Passes: (.+)$", r"推理轮数：\1"),
    (r"^Pass count set to (.+)\.$", r"推理轮数已设置为 \1。"),
    # 最大轮数
    (r"^Max turns set to (.+)\.$", r"最大轮数已设置为 \1。"),
    # 权限
    (r"^Permission mode set to (.+)$", r"权限模式已设置为 \1"),
    (r"^Mode: (.+)$", r"模式：\1"),
    # 会话
    (r"^Session not found: (.+)$", r"未找到会话：\1"),
    (r"^Restored (\d+) messages from session (.+)$", r"已从会话 \2 恢复 \1 条消息"),
    (r"^Restored (\d+) messages from the latest session\.$", r"已从最近会话恢复 \1 条消息。"),
    (r"^Exported transcript to (.+)$", r"已导出转录到 \1"),
    (r"^Created shareable transcript snapshot at (.+)$", r"已创建可分享的转录快照：\1"),
    (r"^Copied (\d+) characters to the clipboard\.$", r"已复制 \1 个字符到剪贴板。"),
    (r"^Clipboard unavailable\. Saved copied text to (.+)$", r"剪贴板不可用，已保存到 \1"),
    (r"^Rewound (\d+) turn\(s\); removed (\d+) message\(s\)\.$", r"已回退 \1 轮，移除 \2 条消息。"),
    (r"^Reverted (\d+) file\(s\)\.$", r"已恢复 \1 个文件。"),
    (r"^Nothing to rewind\.$", r"没有需要回退的内容。"),
    # 任务
    (r"^Started task (.+)$", r"已启动任务 \1"),
    (r"^Stopped task (.+)$", r"已停止任务 \1"),
    (r"^No task found with ID: (.+)$", r"未找到任务 ID：\1"),
    (r"^Updated task (.+) description$", r"已更新任务 \1 的描述"),
    (r"^Updated task (.+) progress to (\d+)%$", r"已更新任务 \1 的进度为 \2%"),
    (r"^Updated task (.+) note$", r"已更新任务 \1 的备注"),
    (r"^Deleted (\d+) session file\(s\)\.$", r"已删除 \1 个会话文件。"),
    (r"^Deleted session: (.+)$", r"已删除会话：\1"),
    (r"^Deleted current session: (.+)$", r"已删除当前会话：\1"),
    # Agent
    (r"^No agent found with ID: (.+)$", r"未找到 agent ID：\1"),
    # Bridge
    (r"^Spawned bridge session (.+) pid=(\d+)$", r"已创建 bridge 会话 \1 进程 \2"),
    (r"^Stopped bridge session (.+)$", r"已停止 bridge 会话 \1"),
    # 插件
    (r"^Enabled plugin '(.+)'\. Restart session to reload\.$", r"已启用插件「\1」，重启会话后生效。"),
    (r"^Disabled plugin '(.+)'\. Restart session to reload\.$", r"已禁用插件「\1」，重启会话后生效。"),
    (r"^Installed plugin to (.+)$", r"已安装插件到 \1"),
    (r"^Uninstalled plugin '(.+)'$", r"已卸载插件「\1」"),
    (r"^Plugin '(.+)' not found$", r"未找到插件「\1」"),
    # 配置
    (r"^Unknown config key: (.+)$", r"未知配置项：\1"),
    (r"^Updated (.+)$", r"已更新 \1"),
    # 记忆
    (r"^Memory entry not found: (.+)$", r"未找到记忆条目：\1"),
    (r"^Added memory entry (.+)$", r"已添加记忆条目 \1"),
    (r"^Removed memory entry (.+)$", r"已移除记忆条目 \1"),
    # MCP
    (r"^Unknown MCP server: (.+)$", r"未知 MCP 服务器：\1"),
    (r"^Server (.+) does not support auth updates$", r"服务器 \1 不支持认证更新"),
    (r"^Saved MCP auth for (.+)\. Restart session to reconnect\.$", r"已保存 \1 的 MCP 认证，重启会话后重新连接。"),
    # Issue 与 PR 评论
    (r"^No issue context\. File path: (.+)$", r"无 issue 上下文。文件路径：\1"),
    (r"^Saved issue context to (.+)$", r"已保存 issue 上下文到 \1"),
    (r"^No PR comments context\. File path: (.+)$", r"无 PR 评论上下文。文件路径：\1"),
    (r"^Added PR comment to (.+)$", r"已添加 PR 评论到 \1"),
    # 反馈
    (r"^Saved feedback to (.+)$", r"已保存反馈到 \1"),
    # 初始化
    (r"^Initialized project files:$", r"已初始化项目文件："),
    (r"^\*\*Illusion Code project initialization complete\.\*\*$", r"✨ **Illusion Code 项目初始化完成**"),
    (r"^- \*\*Languages\*\*: (.+)$", r"- **检测到语言**: \1"),
    (r"^- \*\*Frameworks\*\*: (.+)$", r"- **检测到框架**: \1"),
    (r"^- \*\*Package Manager\*\*: (.+)$", r"- **包管理器**: \1"),
    (r"^- \*\*Build\*\*: `(.+)`$", r"- **构建命令**: `\1`"),
    (r"^- \*\*Test\*\*: `(.+)`$", r"- **测试命令**: `\1`"),
    (r"^- \*\*Lint\*\*: `(.+)`$", r"- **代码检查**: `\1`"),
    (r"^- \*\*Format\*\*: `(.+)`$", r"- **格式化工具**: `\1`"),
    (r"^- \*\*CI/CD\*\*: (.+)$", r"- **CI/CD**: \1"),
    # 技能
    (r"^Skill not found: (.+)$", r"未找到技能：\1"),
    # 规则
    (r"^No rules found in (.+)$", r"在 \1 中未找到规则"),
    (r"^Rule not found: (.+)\. Use /rules to list available rules\.$", r"未找到规则：\1。使用 /rules 查看可用规则。"),
    # 状态行（多行消息的逐行翻译）
    (r"^Session stats:$", r"会话统计："),
    (r"^Messages: (\d+)$", r"消息数：\1"),
    (r"^Usage: input=(\d+) output=(\d+)$", r"用量：输入=\1 输出=\2"),
    (r"^Effort: (.+)$", r"推理强度：\1"),
    (r"^Actual usage: input=(\d+) output=(\d+)$", r"实际用量：输入=\1 输出=\2"),
    (r"^Estimated conversation tokens: (\d+)$", r"预估对话 token：\1"),
    (r"^Input tokens: (\d+)$", r"输入 token：\1"),
    (r"^Output tokens: (\d+)$", r"输出 token：\1"),
    (r"^Total tokens: (\d+)$", r"总计 token：\1"),
    (r"^Estimated cost: (.+)$", r"预估费用：\1"),
    (r"^Max turns \(engine\): (.+)$", r"最大轮数（引擎）：\1"),
    (r"^Max turns \(config\): (.+)$", r"最大轮数（配置）：\1"),
    (r"^Memory directory: (.+)$", r"记忆目录：\1"),
    (r"^Entrypoint: (.+)$", r"入口文件：\1"),
    (r"^Compacted conversation from (\d+) messages to (\d+)\.$", r"已压缩对话：\1 条 → \2 条。"),
    (r"^Compacted conversation from (\d+) to (\d+) messages \(saved ~(\d[\d,]*) tokens\)\.$", r"已压缩对话：\1 → \2 条消息（节省 ~\3 tokens）。"),
    (r"^Current branch: (.+)$", r"当前分支：\1"),
    (r"^Feedback log: (.+)$", r"反馈日志：\1"),
    (r"^Auth status:$", r"认证状态："),
    (r"^Bridge summary:$", r"Bridge 摘要："),
    (r"^Reloaded plugins:$", r"已重新加载插件："),
    (r"^Available skills:$", r"可用技能："),
    (r"^Rules directory: (.+)$", r"规则目录：\1"),
    # 前缀行（doctor, privacy-settings, bridge, login, stats, permissions 等）
    (r"^- backend host: available$", r"- 后端宿主：可用"),
    (r"^- network: enabled only for provider and explicit web/MCP calls$", r"- 网络：仅用于提供商和显式 web/MCP 调用"),
    (r"^- storage: local files under ~\/\.illusion and project \.illusion$", r"- 存储：本地文件位于 ~/.illusion 和项目 .illusion"),
    (r"^- messages: (\d+)$", r"- 消息数：\1"),
    (r"^- estimated_tokens: (\d+)$", r"- 预估 token：\1"),
    (r"^- tools: (\d+)$", r"- 工具数：\1"),
    (r"^- memory_files: (\d+)$", r"- 记忆文件：\1"),
    (r"^- background_tasks: (\d+)$", r"- 后台任务：\1"),
    (r"^- output_style: (.+)$", r"- 输出风格：\1"),
    (r"^- cwd: (.+)$", r"- 工作目录：\1"),
    (r"^- sessions: (\d+)$", r"- 会话数：\1"),
    (r"^- utilities: (.+)$", r"- 工具集：\1"),
    (r"^- provider: (.+)$", r"- 提供商：\1"),
    (r"^- auth_status: (.+)$", r"- 认证状态：\1"),
    (r"^- base_url: (.+)$", r"- 基础 URL：\1"),
    (r"^- model: (.+)$", r"- 模型：\1"),
    (r"^- api_key: (.+)$", r"- API Key：\1"),
    (r"^Allowed tools: (.+)$", r"允许的工具：\1"),
    (r"^Denied tools: (.+)$", r"拒绝的工具：\1"),
    (r"^- permission_mode: (.+)$", r"- 权限模式：\1"),
    (r"^- ui_language: (.+)$", r"- 界面语言：\1"),
    (r"^- memory_dir: (.+)$", r"- 记忆目录：\1"),
    (r"^- plugin_count: (\d+)$", r"- 插件数：\1"),
    (r"^- mcp_configured: (yes|no)$",
     lambda m: f"- MCP 已配置：{'是' if m.group(1) == 'yes' else '否'}"),
    (r"^- user_config_dir: (.+)$", r"- 用户配置目录：\1"),
    (r"^- project_config_dir: (.+)$", r"- 项目配置目录：\1"),
    (r"^- session_dir: (.+)$", r"- 会话目录：\1"),
    (r"^- feedback_log: (.+)$", r"- 反馈日志：\1"),
    (r"^- api_base_url: (.+)$", r"- API 基础 URL：\1"),
    # 沙箱
    (r"^Sandbox status: (.+)$", r"沙箱状态：\1"),
    (r"^  Enabled platforms: (.+)$", r"  限制平台：\1"),
    (r"^  Excluded commands \((\d+)\):$", r"  排除命令（\1）："),
    (r"^  Allow write: (.+)$", r"  允许写入：\1"),
    (r"^  Deny write: (.+)$", r"  拒绝写入：\1"),
    (r"^  Deny read: (.+)$", r"  拒绝读取：\1"),
    (r"^  Allowed domains: (.+)$", r"  允许域名：\1"),
    (r"^  Denied domains: (.+)$", r"  拒绝域名：\1"),
    (r"^Added excluded command: (.+)$", r"已添加排除命令：\1"),
    (r"^Current excluded list: (.+)$", r"当前排除列表：\1"),
    (r"^Removed excluded command: (.+)$", r"已移除排除命令：\1"),
    (r"^Command pattern '(.+)' is already in the excluded list$", r"命令模式「\1」已在排除列表中"),
    (r"^Command pattern '(.+)' is not in the excluded list$", r"命令模式「\1」不在排除列表中"),
    (r"^Sandbox restriction: '(.+)' is blocked by sandbox configuration\.$", r"沙箱限制：「\1」被沙箱配置阻止。"),
    (r"^Tool: (.+)$", r"工具：\1"),
    (r"^Do you want to allow this operation\?$", r"是否允许此操作？"),
    (r"^Sandbox denied: (.+)$", r"沙箱已拒绝：\1"),
]


def _get_lang() -> str:
    """获取当前 ui_language，避免循环导入"""
    from illusion.config.settings import load_settings
    settings = load_settings()
    return settings.ui_language or "en-US"


def t(key: str, **kwargs: Any) -> str:
    """根据 ui_language 返回对应语言的文本

    Args:
        key: 消息键名
        **kwargs: 格式化参数

    Returns:
        str: 对应语言的文本，未找到时返回 key 本身
    """
    lang = _get_lang()
    msg = MESSAGES.get(key, {}).get(lang, MESSAGES.get(key, {}).get("en-US", key))
    if kwargs:
        return msg.format(**kwargs)
    return msg


def _is_zh(locale: str) -> bool:
    return locale.lower().startswith("zh")


def _translate_single_line(line: str) -> str:
    """翻译单行命令消息（英文 -> 当前语言）"""
    if line in _COMMAND_EXACT:
        return _COMMAND_EXACT[line]
    translated = line
    for pattern_str, replacement in _COMMAND_SUBSTITUTIONS:
        pattern = re.compile(pattern_str)
        if callable(replacement):
            translated = pattern.sub(replacement, translated)
        else:
            translated = pattern.sub(replacement, translated)
    return translated


def translate_command_message(message: str, *, locale: str) -> str:
    """翻译命令处理器输出的消息

    对于中文 locale，将英文输出翻译为中文；其他语言原样返回。
    支持多行消息：按行分割，逐行翻译，重新拼接。

    Args:
        message: 命令处理器的英文输出
        locale: 当前 UI 语言

    Returns:
        str: 翻译后的消息
    """
    if not message or not _is_zh(locale):
        return message
    lines = message.split("\n")
    translated_lines = [_translate_single_line(line) for line in lines]
    return "\n".join(translated_lines)
