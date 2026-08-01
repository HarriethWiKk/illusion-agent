""" /btw 侧问命令处理器

在不打断主对话的前提下发起一次性侧问，LLM 回复不写入会话记录。
"""
from __future__ import annotations

import logging

from illusion.commands.types import CommandContext, CommandResult
from illusion.services.side_question import SideQuestionError, run_side_question

logger = logging.getLogger(__name__)


async def btw_handler(args: str, context: CommandContext) -> CommandResult:
    """处理 /btw <question> 命令。

    Args:
        args: 命令参数（侧问内容）
        context: 命令上下文

    Returns:
        CommandResult: ephemeral=True 的临时回复，或错误消息
    """
    question = args.strip()
    if not question:
        return CommandResult(message="Usage: /btw <your question>")
    try:
        reply = await run_side_question(
            question, context.engine, getattr(context, "app_state", None)
        )
    except SideQuestionError as exc:
        return CommandResult(message=f"Side question failed: {exc}")
    return CommandResult(message=reply)
