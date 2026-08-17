"""
Goal 斜杠命令
=============

用法：`/goal [<objective>|clear|edit <objective>|pause|resume]`。

人类命令路径：创建 / edit / pause / resume / clear 均为 human 权威操作；
创建与 resume 返回 drive_goal=True，由 handle_line 立即驱动 goal 轮次。
"""

from __future__ import annotations

from illusion.commands.types import CommandContext, CommandResult
from illusion.engine.query_engine import QueryEngine
from illusion.goal.manager import GoalManager
from illusion.goal.types import GoalError

USAGE = "Usage: /goal [<objective>|clear|edit <objective>|pause|resume]"


def _manager(context: CommandContext) -> tuple[QueryEngine, GoalManager | None]:
    engine = context.engine
    manager = getattr(engine, "_goal_manager", None)
    return engine, manager


def _status_line(manager: GoalManager) -> str:
    view = manager.get_view()
    if view is None:
        return "No goal is currently set."
    lines = [
        f"Objective: {view.snapshot.objective}",
        f"Phase: {view.snapshot.phase} (activation: {view.activation})",
        f"Rounds: {view.rounds_started}/{view.snapshot.max_goal_rounds} · revision {view.snapshot.revision}",
    ]
    if view.snapshot.blocked_reason is not None:
        lines.append(
            f"Blocked: {view.snapshot.blocked_reason.message} (code: {view.snapshot.blocked_reason.code})"
        )
    return "\n".join(lines)


async def goal_handler(args: str, context: CommandContext) -> CommandResult:
    """处理 /goal 命令。"""
    _engine, manager = _manager(context)
    if manager is None:
        return CommandResult(message="Goal feature is disabled (goal.enabled=false).")
    # 命令是人类操作：确保权威来源为 human
    manager.current_source = "human"

    args = (args or "").strip()
    if not args:
        return CommandResult(message=_status_line(manager))

    parts = args.split(maxsplit=1)
    head = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""

    try:
        if head == "clear":
            manager.clear()
            return CommandResult(message="Goal cleared.")
        if head == "pause":
            view = manager.get_view()
            if view is None:
                return CommandResult(message="No goal is currently set.")
            manager.pause(view.snapshot.id, view.snapshot.revision)
            return CommandResult(message="Goal paused.")
        if head == "resume":
            view = manager.get_view()
            if view is None:
                return CommandResult(message="No goal is currently set.")
            manager.resume(view.snapshot.id, view.snapshot.revision)
            return CommandResult(
                message="Goal resumed. Continuing autonomous rounds…",
                drive_goal=True,
            )
        if head == "edit":
            if not rest:
                return CommandResult(message=f"edit requires a new objective.\n\n{USAGE}")
            view = manager.get_view()
            if view is None:
                return CommandResult(message="No goal is currently set.")
            manager.edit(view.snapshot.id, view.snapshot.revision, objective=rest)
            return CommandResult(message="Goal objective updated.")
        # 其余整体视作 objective
        manager.create(objective=args)
        return CommandResult(
            message="Goal set. Starting autonomous rounds…",
            drive_goal=True,
        )
    except GoalError as exc:
        return CommandResult(message=f"{exc.message} (code: {exc.code})")
