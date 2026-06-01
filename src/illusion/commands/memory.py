"""
记忆管理斜杠命令
================

/memory — 查看和管理项目记忆
"""

from __future__ import annotations

from illusion.commands.types import CommandContext, CommandResult
from illusion.memory import (
    add_memory_entry,
    get_memory_entrypoint,
    get_project_memory_dir,
    list_memory_files,
    remove_memory_entry,
)


async def memory_handler(args: str, context: CommandContext) -> CommandResult:
    """记忆管理命令处理器"""
    tokens = args.split(maxsplit=1)
    if not tokens:
        memory_dir = get_project_memory_dir(context.cwd)
        entrypoint = get_memory_entrypoint(context.cwd)
        return CommandResult(
            message=f"Memory directory: {memory_dir}\nEntrypoint: {entrypoint}"
        )
    action = tokens[0]
    rest = tokens[1] if len(tokens) == 2 else ""
    if action == "list":
        memory_files = list_memory_files(context.cwd)
        if not memory_files:
            return CommandResult(message="No memory files.")
        return CommandResult(message="\n".join(path.name for path in memory_files))
    if action == "show" and rest:
        memory_dir = get_project_memory_dir(context.cwd)
        path = memory_dir / rest
        if not path.exists():
            path = memory_dir / f"{rest}.md"
        if not path.exists():
            return CommandResult(message=f"Memory entry not found: {rest}")
        return CommandResult(message=path.read_text(encoding="utf-8"))
    if action == "add" and rest:
        title, separator, content = rest.partition("::")
        if not separator or not title.strip() or not content.strip():
            return CommandResult(message="Usage: /memory add TITLE :: CONTENT")
        path = add_memory_entry(context.cwd, title.strip(), content.strip())
        return CommandResult(message=f"Added memory entry {path.name}")
    if action == "remove" and rest:
        if remove_memory_entry(context.cwd, rest.strip()):
            return CommandResult(message=f"Removed memory entry {rest.strip()}")
        return CommandResult(message=f"Memory entry not found: {rest.strip()}")
    return CommandResult(message="Usage: /memory [list|show NAME|add TITLE :: CONTENT|remove NAME]")
