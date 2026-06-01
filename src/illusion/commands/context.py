"""
上下文管理斜杠命令
==================

/issue, /pr_comments
"""

from __future__ import annotations

from illusion.commands.types import CommandContext, CommandResult
from illusion.config.paths import get_project_issue_file, get_project_pr_comments_file


async def issue_handler(args: str, context: CommandContext) -> CommandResult:
    """显示或更新项目 issue 上下文"""
    path = get_project_issue_file(context.cwd)
    tokens = args.split(maxsplit=1)
    action = tokens[0] if tokens else "show"
    rest = tokens[1] if len(tokens) == 2 else ""
    if action == "show":
        if not path.exists():
            return CommandResult(message=f"No issue context. File path: {path}")
        return CommandResult(message=path.read_text(encoding="utf-8"))
    if action == "set" and rest:
        title, separator, body = rest.partition("::")
        if not separator or not title.strip() or not body.strip():
            return CommandResult(message="Usage: /issue set TITLE :: BODY")
        content = f"# {title.strip()}\n\n{body.strip()}\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return CommandResult(message=f"Saved issue context to {path}")
    if action == "clear":
        if path.exists():
            path.unlink()
            return CommandResult(message="Cleared issue context.")
        return CommandResult(message="No issue context to clear.")
    return CommandResult(message="Usage: /issue [show|set TITLE :: BODY|clear]")


async def pr_comments_handler(args: str, context: CommandContext) -> CommandResult:
    """显示或更新项目 PR 评论上下文"""
    path = get_project_pr_comments_file(context.cwd)
    tokens = args.split(maxsplit=1)
    action = tokens[0] if tokens else "show"
    rest = tokens[1] if len(tokens) == 2 else ""
    if action == "show":
        if not path.exists():
            return CommandResult(message=f"No PR comments context. File path: {path}")
        return CommandResult(message=path.read_text(encoding="utf-8"))
    if action == "add" and rest:
        location, separator, comment = rest.partition("::")
        if not separator or not location.strip() or not comment.strip():
            return CommandResult(message="Usage: /pr_comments add FILE[:LINE] :: COMMENT")
        existing = path.read_text(encoding="utf-8") if path.exists() else "# PR Comments\n"
        if not existing.endswith("\n"):
            existing += "\n"
        existing += f"- {location.strip()}: {comment.strip()}\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(existing, encoding="utf-8")
        return CommandResult(message=f"Added PR comment to {path}")
    if action == "clear":
        if path.exists():
            path.unlink()
            return CommandResult(message="Cleared PR comments context.")
        return CommandResult(message="No PR comments context to clear.")
    return CommandResult(message="Usage: /pr_comments [show|add FILE[:LINE] :: COMMENT|clear]")
