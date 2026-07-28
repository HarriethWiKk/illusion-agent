"""
Git 相关斜杠命令
================

/diff, /branch, /commit
"""

from __future__ import annotations

from illusion.commands.helpers import run_git_command
from illusion.commands.types import CommandContext, CommandResult


async def diff_handler(args: str, context: CommandContext) -> CommandResult:
    """显示 git diff"""
    if args.strip() == "full":
        ok, output = run_git_command(context.cwd, "diff", "HEAD")
        return CommandResult(message=output or "(no diff)")
    ok, output = run_git_command(context.cwd, "diff", "--stat")
    if not ok:
        return CommandResult(message=output)
    return CommandResult(message=output or "(no diff)")


async def branch_handler(args: str, context: CommandContext) -> CommandResult:
    """显示 git 分支信息"""
    action = args.strip() or "show"
    if action == "show":
        ok, current = run_git_command(context.cwd, "branch", "--show-current")
        if not ok:
            return CommandResult(message=current)
        return CommandResult(message=f"Current branch: {current or '(detached HEAD)'}")
    if action == "list":
        ok, branches = run_git_command(context.cwd, "branch", "--format", "%(refname:short)")
        return CommandResult(message=branches)
    return CommandResult(message="Usage: /branch [show|list]")


async def commit_handler(args: str, context: CommandContext) -> CommandResult:
    """显示状态或创建 git commit"""
    message = args.strip()
    if not message:
        ok, status = run_git_command(context.cwd, "status", "--short")
        return CommandResult(message=status if ok and status else "(working tree clean)")
    ok, status = run_git_command(context.cwd, "status", "--short")
    if not ok:
        return CommandResult(message=status)
    if not status.strip():
        return CommandResult(message="Nothing to commit.")
    ok, output = run_git_command(context.cwd, "add", "-A")
    if not ok:
        return CommandResult(message=output)
    ok, output = run_git_command(context.cwd, "commit", "-m", message)
    return CommandResult(message=output)
