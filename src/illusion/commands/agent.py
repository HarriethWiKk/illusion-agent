""" /agent 命令处理器

查看已完成 agent 的摘要，或引导用户创建新 agent。

路由：
    - 无参数 / list：提示用法（前端可通过 select_command('agent') 列出可选项）
    - create / new：提示创建向导由前端驱动（agent_wizard_init/submit）
    - <id>：双数据源查询
        - 前台 agent：<id> 为 tool_use_id，从 engine.messages 提取对应 tool_result
        - 后台 agent：<id> 为 task_id，从 transcript 的 task-notification 提取 <result>
          （task-notification 是后端在 agent 完成时注入的 user 消息 TextBlock，
           天然随会话同步，避免 manager._tasks 进程级单例跨会话不同步问题）
"""
from __future__ import annotations

from illusion.commands.types import CommandContext, CommandResult
from illusion.engine.messages import TextBlock, ToolResultBlock
from illusion.tasks.types import TASK_NOTIFICATION_RE


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
    #    跳过 "launched in background/as subprocess" 启动通知（非摘要，
    #    与 select_command('agent') 的前台过滤逻辑保持一致）
    for msg in context.engine.messages:
        if msg.role != "user":
            continue
        for block in msg.content:
            if isinstance(block, ToolResultBlock) and block.tool_use_id == query_id:
                text = block.text_content
                if text and ("launched in background" in text or "launched as subprocess" in text):
                    continue  # 启动通知非摘要，跳过继续查找 task-notification
                if text:
                    return CommandResult(message=text)
                return CommandResult(message=f"Agent tool result '{query_id}' is empty.")

    # 2. 后台 agent：从 transcript 的 task-notification 提取 <result> 内容
    #    task-notification 是后端在 agent 完成时注入的 user 消息 TextBlock，
    #    天然随会话同步，避免 manager._tasks 进程级单例跨会话不同步问题。
    for msg in context.engine.messages:
        if msg.role != "user":
            continue
        for block in msg.content:
            if not isinstance(block, TextBlock):
                continue
            match = TASK_NOTIFICATION_RE.search(block.text)
            if not match:
                continue
            task_id = match.group(1).strip()
            if task_id != query_id:
                continue
            status = match.group(2).strip()
            if status != "completed":
                return CommandResult(message=f"Agent '{query_id}' is not completed (status: {status}).")
            result_text = match.group(4).strip()
            return CommandResult(message=result_text or f"Agent '{query_id}' has no captured output.")

    # 3. 找不到
    return CommandResult(message=f"No task found with id: {query_id}")
