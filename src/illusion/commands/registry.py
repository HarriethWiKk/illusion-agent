"""
斜杠命令注册模块
==============

本模块提供斜杠命令的注册和管理功能。

主要组件：
    - SlashCommand: 斜杠命令定义
    - CommandRegistry: 命令注册表
    - create_default_command_registry: 创建默认命令注册表

命令实现在各子模块中：
    - session.py: /new, /status, /context, /summary, /compact, /resume, /rewind, /delete
    - git.py: /diff, /branch, /commit
    - settings.py: /config, /language, /output-style, /privacy-settings, /doctor, /thinking, /effort, /max-tokens, /passes, /turns, /permissions, /plan
    - auth.py: /login, /logout
    - context.py: /issue, /pr_comments
    - misc.py: /exit, /version, /copy, /export, /share, /feedback, /help, /hooks, /reload-plugins, /skills, /files, /continue, /update
    - bridge.py: /bridge
    - mcp.py: /mcp
    - plugin.py: /plugin
    - model.py: /model
    - memory.py: /memory
    - rules.py: /rules
    - sandbox.py: /sandbox
    - init/: /init

使用示例：
    >>> from illusion.commands import create_default_command_registry
    >>> registry = create_default_command_registry()
    >>> result = registry.lookup("/version")
"""

from __future__ import annotations

from dataclasses import dataclass

from illusion.commands.types import CommandContext, CommandHandler, CommandResult
from illusion.config.i18n import (
    COMMAND_DESCRIPTIONS_ZH,
    _is_zh,
    translate_command_message,
)
from illusion.config.settings import load_settings


def _resolve_ui_language(context: CommandContext | None) -> str:
    if context is not None and context.app_state is not None:
        value = str(context.app_state.get().ui_language or "")
        if value:
            return value
    return str(load_settings().ui_language)


def _translate_command_message(message: str, *, locale: str) -> str:
    """翻译命令消息（委托给 i18n 模块）"""
    return translate_command_message(message, locale=locale)


@dataclass
class SlashCommand:
    """斜杠命令定义

    Attributes:
        name: 命令名称 (不含前导/)
        description: 命令描述
        handler: 命令处理器函数
    """

    name: str  # 命令名称
    description: str  # 命令描述
    handler: CommandHandler  # 处理器函数


class CommandRegistry:
    """斜杠命令到处理器的映射容器

    Attributes:
        _commands: 命令名到SlashCommand的映射
    """

    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}

    def register(self, command: SlashCommand) -> None:
        """注册命令

        Args:
            command: 要注册的SlashCommand
        """
        original_handler = command.handler

        async def _localized_handler(args: str, context: CommandContext) -> CommandResult:
            result = await original_handler(args, context)
            if result.message:
                result.message = _translate_command_message(
                    result.message,
                    locale=_resolve_ui_language(context),
                )
            return result

        self._commands[command.name] = SlashCommand(
            name=command.name,
            description=command.description,
            handler=_localized_handler,
        )

    def lookup(self, raw_input: str) -> tuple[SlashCommand, str] | None:
        """解析斜杠命令并返回其处理器和原始参数

        Args:
            raw_input: 原始输入字符串

        Returns:
            tuple[SlashCommand, str] | None: (命令对象, 参数) 或 None
        """
        if not raw_input.startswith("/"):
            return None
        name, _, args = raw_input[1:].partition(" ")
        command = self._commands.get(name)
        if command is None:
            return None
        return command, args.strip()

    def help_text(self) -> str:
        """返回所有已注册命令的格式化摘要

        Returns:
            str: 格式化的命令帮助文本
        """
        locale = _resolve_ui_language(None)
        lines = ["可用命令：" if _is_zh(locale) else "Available commands:"]
        for command in sorted(self._commands.values(), key=lambda item: item.name):
            description = command.description
            if _is_zh(locale):
                description = COMMAND_DESCRIPTIONS_ZH.get(command.name, description)
            lines.append(f"/{command.name:<12} {description}")
        return "\n".join(lines)

    def list_commands(self) -> list[SlashCommand]:
        """按照注册顺序返回命令列表

        Returns:
            list[SlashCommand]: 命令列表
        """
        return list(self._commands.values())


def create_default_command_registry() -> CommandRegistry:
    """Create the built-in command registry."""
    registry = CommandRegistry()

    # --- 会话管理 ---
    # --- 认证 ---
    from illusion.commands.auth import login_handler, logout_handler

    # --- Bridge ---
    from illusion.commands.bridge import bridge_handler

    # --- 上下文 ---
    from illusion.commands.context import issue_handler, pr_comments_handler

    # --- Git ---
    from illusion.commands.git import (
        branch_handler,
        commit_handler,
        diff_handler,
    )

    # --- Init ---
    from illusion.commands.init import run_init

    # --- MCP ---
    from illusion.commands.mcp import mcp_handler

    # --- 记忆 ---
    from illusion.commands.memory import memory_handler

    # --- 杂项 ---
    from illusion.commands.misc import (
        continue_handler,
        copy_handler,
        exit_handler,
        export_handler,
        feedback_handler,
        files_handler,
        hooks_handler,
        make_help_handler,
        reload_plugins_handler,
        share_handler,
        skills_handler,
        update_handler,
        version_handler,
    )

    # --- 模型 ---
    from illusion.commands.model import model_handler

    # --- 插件 ---
    from illusion.commands.plugin import plugin_handler

    # --- 规则 ---
    from illusion.commands.rules import rules_handler

    # --- 沙箱 ---
    from illusion.commands.sandbox import sandbox_handler
    from illusion.commands.session import (
        compact_handler,
        context_handler,
        delete_handler,
        new_handler,
        resume_handler,
        rewind_handler,
        status_handler,
        summary_handler,
    )

    # --- 设置 ---
    from illusion.commands.settings import (
        config_handler,
        doctor_handler,
        effort_handler,
        language_handler,
        max_tokens_handler,
        output_style_handler,
        passes_handler,
        permissions_handler,
        plan_handler,
        privacy_settings_handler,
        thinking_handler,
        turns_handler,
    )

    async def _init_handler(args: str, context: CommandContext) -> CommandResult:
        """智能初始化项目配置"""
        del args
        return await run_init(context)

    # --- 注册所有命令 ---
    registry.register(SlashCommand("exit", "Exit IllusionCode", exit_handler))
    registry.register(SlashCommand("clear", "Clear conversation and start a new session", new_handler))
    registry.register(SlashCommand("new", "Start a new conversation session", new_handler))
    registry.register(SlashCommand("version", "Show the installed IllusionCode version", version_handler))
    registry.register(SlashCommand("status", "Show session status", status_handler))
    registry.register(SlashCommand("context", "Show active system prompt or manage context window", context_handler))
    registry.register(SlashCommand("summary", "Summarize conversation history", summary_handler))
    registry.register(SlashCommand("compact", "Compact older conversation history", compact_handler))
    registry.register(SlashCommand("memory", "Inspect and manage project memory", memory_handler))
    registry.register(SlashCommand("hooks", "Show configured hooks", hooks_handler))
    registry.register(SlashCommand("resume", "Restore the latest saved session", resume_handler))
    registry.register(SlashCommand("export", "Export the current transcript", export_handler))
    registry.register(SlashCommand("share", "Create a shareable transcript snapshot", share_handler))
    registry.register(SlashCommand("copy", "Copy the latest response or provided text", copy_handler))
    registry.register(SlashCommand("rewind", "Remove the latest conversation turn(s)", rewind_handler))
    registry.register(SlashCommand("files", "List files in the current workspace", files_handler))
    registry.register(SlashCommand("init", "Initialize project IllusionCode files", _init_handler))
    registry.register(SlashCommand("bridge", "Inspect bridge helpers and spawn bridge sessions", bridge_handler))
    registry.register(SlashCommand("login", "Show auth status or store an API key", login_handler))
    registry.register(SlashCommand("logout", "Clear the stored API key", logout_handler))
    registry.register(SlashCommand("feedback", "Save CLI feedback to the local feedback log", feedback_handler))
    registry.register(SlashCommand("skills", "List or show available skills", skills_handler))
    registry.register(SlashCommand("config", "Show or update configuration", config_handler))
    registry.register(SlashCommand("mcp", "Show MCP status", mcp_handler))
    registry.register(SlashCommand("plugin", "Manage plugins", plugin_handler))
    registry.register(SlashCommand("reload-plugins", "Reload plugin discovery for this workspace", reload_plugins_handler))
    registry.register(SlashCommand("permissions", "Show or update permission mode", permissions_handler))
    registry.register(SlashCommand("plan", "Toggle plan permission mode", plan_handler))
    registry.register(SlashCommand("thinking", "Show or update thinking mode", thinking_handler))
    registry.register(SlashCommand("effort", "Show or update reasoning effort", effort_handler))
    registry.register(SlashCommand("max-tokens", "Show or update max output tokens", max_tokens_handler))
    registry.register(SlashCommand("passes", "Show or update reasoning pass count", passes_handler))
    registry.register(SlashCommand("turns", "Show or update maximum agentic turn count", turns_handler))
    registry.register(SlashCommand("continue", "Continue the previous tool loop if it was interrupted", continue_handler))
    registry.register(SlashCommand("model", "Show or update the default model", model_handler))
    registry.register(SlashCommand("language", "Show or update UI language", language_handler))
    registry.register(SlashCommand("output-style", "Show or update output style", output_style_handler))
    registry.register(SlashCommand("doctor", "Show environment diagnostics", doctor_handler))
    registry.register(SlashCommand("diff", "Show git diff output", diff_handler))
    registry.register(SlashCommand("branch", "Show git branch information", branch_handler))
    registry.register(SlashCommand("commit", "Show status or create a git commit", commit_handler))
    registry.register(SlashCommand("issue", "Show or update project issue context", issue_handler))
    registry.register(SlashCommand("pr_comments", "Show or update project PR comments context", pr_comments_handler))
    registry.register(SlashCommand("privacy-settings", "Show local privacy and storage settings", privacy_settings_handler))
    registry.register(SlashCommand("delete", "Delete saved sessions", delete_handler))
    registry.register(SlashCommand("rules", "View project rules", rules_handler))
    registry.register(SlashCommand("sandbox", "Show sandbox status or manage excluded commands", sandbox_handler))
    registry.register(SlashCommand("update", "Check for and install IllusionCode updates", update_handler))

    # /help 需要引用 registry 实例
    help_handler = make_help_handler(registry)
    registry.register(SlashCommand("help", "Show available commands and their usage", help_handler))

    return registry
