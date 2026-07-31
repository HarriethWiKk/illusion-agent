""" /agent 命令处理器

查看已完成 agent 的摘要，或引导用户创建新 agent。

路由：
    - 无参数 / list：提示用法（前端可通过 select_command('agent') 列出可选项）
    - create / new：提示创建向导由前端驱动（agent_wizard_init/submit）
    - <task_id>：直接返回指定 agent 的摘要文本
"""
from __future__ import annotations

from illusion.commands.types import CommandContext, CommandResult
from illusion.tasks.manager import get_task_manager


async def agent_handler(args: str, context: CommandContext) -> CommandResult:
    """处理 /agent 命令。

    Args:
        args: 命令参数（空 / list / create / new / <task_id>）
        context: 命令上下文

    Returns:
        CommandResult: 摘要消息或引导提示
    """
    del context  # 当前路由无需上下文，保留参数以符合 CommandHandler 签名
    tokens = args.strip().split()
    if not tokens or tokens[0] == "list":
        return CommandResult(
            message=(
                "Use /agent <task_id> to view a completed agent's summary, "
                "or /agent create to create a new agent."
            )
        )
    if tokens[0] in ("create", "new"):
        return CommandResult(
            message="Agent creation wizard triggered via UI. Use the agent_wizard_init request to begin."
        )
    # 按 task_id 查询摘要
    task_id = tokens[0]
    manager = get_task_manager()
    record = manager._tasks.get(task_id)
    if record is None:
        return CommandResult(message=f"No task found with id: {task_id}")
    summary = getattr(record, "summary", None) or getattr(record, "result", None)
    if not summary:
        return CommandResult(message=f"Agent '{task_id}' has no captured summary.")
    return CommandResult(message=summary)
