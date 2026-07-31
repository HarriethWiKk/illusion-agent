""" /agent 命令处理器

查看已完成 agent 的摘要，或引导用户创建新 agent。

路由：
    - 无参数 / list：提示用法（前端可通过 select_command('agent') 列出可选项）
    - create / new：提示创建向导由前端驱动（agent_wizard_init/submit）
    - <id>：双数据源查询
        - 前台 agent：<id> 为 tool_use_id，从 engine.messages 提取对应 tool_result
        - 后台 agent：<id> 为 task_id，从 TaskRecord 读取（复用 read_task_output）
"""
from __future__ import annotations

from illusion.commands.types import CommandContext, CommandResult
from illusion.engine.messages import ToolResultBlock
from illusion.tasks.manager import get_task_manager


async def agent_handler(args: str, context: CommandContext) -> CommandResult:
    """处理 /agent 命令。

    Args:
        args: 命令参数（空 / list / create / new / <id>）
        context: 命令上下文

    Returns:
        CommandResult: 摘要消息或引导提示
    """
    tokens = args.strip().split()
    if not tokens or tokens[0] == "list":
        return CommandResult(
            message=(
                "Use /agent <id> to view a completed agent's summary, "
                "or /agent create to create a new agent."
            )
        )
    if tokens[0] in ("create", "new"):
        return CommandResult(
            message="Agent creation wizard triggered via UI. Use the agent_wizard_init request to begin."
        )

    query_id = tokens[0]

    # 1. 前台 agent：从 transcript 找 tool_use_id 匹配的 tool_result
    for msg in context.engine.messages:
        if msg.role != "user":
            continue
        for block in msg.content:
            if isinstance(block, ToolResultBlock) and block.tool_use_id == query_id:
                text = block.text_content
                if text:
                    return CommandResult(message=text)
                return CommandResult(message=f"Agent tool result '{query_id}' is empty.")

    # 2. 后台 agent：从 TaskRecord 读取（复用 task_output 逻辑）
    manager = get_task_manager()
    record = manager._tasks.get(query_id)
    if record is None:
        return CommandResult(message=f"No task found with id: {query_id}")
    if record.type not in ("in_process_agent", "local_agent"):
        return CommandResult(message=f"Task '{query_id}' is not an agent task.")
    if record.status != "completed":
        return CommandResult(message=f"Agent '{query_id}' is not completed (status: {record.status}).")
    try:
        output = manager.read_task_output(query_id)
    except ValueError as exc:
        return CommandResult(message=str(exc))
    return CommandResult(message=output or f"Agent '{query_id}' has no captured output.")
