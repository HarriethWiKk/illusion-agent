"""
杂项斜杠命令
============

/exit, /version, /copy, /export, /share, /feedback,
/help, /hooks, /reload-plugins, /skills, /files, /continue
"""

from __future__ import annotations

import importlib.metadata
from datetime import datetime, timezone
from pathlib import Path

from illusion.commands.helpers import copy_to_clipboard, last_message_text
from illusion.commands.types import CommandContext, CommandResult
from illusion.config.settings import load_settings
from illusion.config.paths import get_feedback_log_path
from illusion.plugins import load_plugins
from illusion.services import export_session_markdown
from illusion.skills import load_skill_registry


async def exit_handler(_: str, context: CommandContext) -> CommandResult:
    """退出程序"""
    del context
    return CommandResult(should_exit=True)


async def version_handler(_: str, context: CommandContext) -> CommandResult:
    """显示版本号"""
    del context
    try:
        version = importlib.metadata.version("illusion")
    except importlib.metadata.PackageNotFoundError:
        version = "0.1.0"
    return CommandResult(message=f"IllusionCode {version}")


async def copy_handler(args: str, context: CommandContext) -> CommandResult:
    """复制最新回复或指定文本"""
    text = args.strip() or last_message_text(context.engine.messages)
    if not text:
        return CommandResult(message="Nothing to copy.")
    copied, target = copy_to_clipboard(text)
    if copied:
        return CommandResult(message=f"Copied {len(text)} characters to the clipboard.")
    return CommandResult(message=f"Clipboard unavailable. Saved copied text to {target}")


async def export_handler(_: str, context: CommandContext) -> CommandResult:
    """导出当前转录"""
    path = export_session_markdown(cwd=context.cwd, messages=context.engine.messages)
    return CommandResult(message=f"Exported transcript to {path}")


async def share_handler(_: str, context: CommandContext) -> CommandResult:
    """创建可分享的转录快照"""
    path = export_session_markdown(cwd=context.cwd, messages=context.engine.messages)
    return CommandResult(message=f"Created shareable transcript snapshot at {path}")


async def feedback_handler(args: str, context: CommandContext) -> CommandResult:
    """保存 CLI 反馈"""
    del context
    path = get_feedback_log_path()
    if not args.strip():
        return CommandResult(message=f"Feedback log: {path}\nUsage: /feedback TEXT")
    timestamp = datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {args.strip()}\n")
    return CommandResult(message=f"Saved feedback to {path}")


def make_help_handler(registry):
    """创建 help 命令处理器（需要引用 registry 实例）"""

    async def help_handler(args: str, context: CommandContext) -> CommandResult:
        """显示可用命令"""
        return CommandResult(message=registry.help_text())

    return help_handler


async def hooks_handler(_: str, context: CommandContext) -> CommandResult:
    """显示已配置的 hooks"""
    return CommandResult(message=context.hooks_summary or "No hooks configured.")


async def reload_plugins_handler(_: str, context: CommandContext) -> CommandResult:
    """重新加载插件"""
    settings = load_settings()
    plugins = load_plugins(settings, context.cwd)
    if not plugins:
        return CommandResult(message="No plugins discovered.")
    lines = ["Reloaded plugins:"]
    for plugin in plugins:
        state = "enabled" if plugin.enabled else "disabled"
        lines.append(f"- {plugin.manifest.name} [{state}]")
    return CommandResult(message="\n".join(lines))


async def skills_handler(args: str, context: CommandContext) -> CommandResult:
    """列出或显示可用技能"""
    skill_registry = load_skill_registry(context.cwd)
    if args:
        skill = skill_registry.get(args)
        if skill is None:
            return CommandResult(message=f"Skill not found: {args}")
        return CommandResult(message=skill.content)
    skills = skill_registry.list_skills()
    if not skills:
        return CommandResult(message="No skills available.")
    lines = ["Available skills:"]
    for skill in skills:
        source = f" [{skill.source}]"
        lines.append(f"- {skill.name}{source}: {skill.description}")
    return CommandResult(message="\n".join(lines))


async def files_handler(args: str, context: CommandContext) -> CommandResult:
    """列出当前工作区文件"""
    raw = args.strip()
    root = Path(context.cwd)
    max_items = 30
    tokens = raw.split(maxsplit=1)
    if tokens and tokens[0] == "dirs":
        dirs = [
            path
            for path in sorted(root.rglob("*"))
            if path.is_dir() and ".git" not in path.parts and ".venv" not in path.parts
        ]
        lines = [str(path.relative_to(root)) for path in dirs[:max_items]]
        if len(dirs) > max_items:
            lines.append(f"... {len(dirs) - max_items} more")
        return CommandResult(message="\n".join(lines) if lines else "(no directories)")
    if tokens and tokens[0].isdigit():
        max_items = max(1, min(int(tokens[0]), 200))
        raw = tokens[1] if len(tokens) == 2 else ""
    needle = raw.lower()
    files = [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.parts and ".venv" not in path.parts
    ]
    if needle:
        files = [path for path in files if needle in str(path.relative_to(root)).lower()]
    lines = [str(path.relative_to(root)) for path in files[:max_items]]
    if len(files) > max_items:
        lines.append(f"... {len(files) - max_items} more")
    return CommandResult(
        message="\n".join(lines) if lines else "(no matching files)"
    )


async def continue_handler(args: str, context: CommandContext) -> CommandResult:
    """继续被中断的工具循环"""
    raw = args.strip()
    if not context.engine.has_pending_continuation():
        return CommandResult(message="Nothing to continue (no pending tool results).")

    turns: int | None = None
    if raw:
        tokens = raw.split()
        if tokens[0] == "set" and len(tokens) == 2:
            raw = tokens[1]
        try:
            turns = int(raw)
        except ValueError:
            return CommandResult(message="Usage: /continue [COUNT]")
        turns = max(1, min(turns, 512))

    return CommandResult(
        message="Continuing pending tool loop...",
        continue_pending=True,
        continue_turns=turns,
    )
