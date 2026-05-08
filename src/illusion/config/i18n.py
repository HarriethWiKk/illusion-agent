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

from typing import Any

# i18n 消息表
MESSAGES: dict[str, dict[str, str]] = {
    # --- auth ---
    "select_provider": {"zh-CN": "选择提供商:", "en-US": "Select a provider:"},
    "custom_provider": {"zh-CN": "自定义提供商", "en-US": "Custom provider"},
    "anthropic_label": {"zh-CN": "Anthropic (Claude API)", "en-US": "Anthropic (Claude API)"},
    "openai_label": {"zh-CN": "OpenAI / 兼容接口", "en-US": "OpenAI / compatible"},
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
}


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
