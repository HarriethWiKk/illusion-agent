"""
/btw 侧问命令处理器
===================

在不打断主对话的前提下发起一次性侧问，LLM 回复不写入会话记录。

核心设计：
    - 复用当前会话的 QueryEngine 配置（API 客户端、工具注册表、权限检查器）
    - 独立的 file_state_cache，避免污染主会话状态
    - deny_all_tools=True，拒绝所有工具调用，防止工作区污染
    - 返回结果标记 ephemeral=True，前端可区分临时回复与正式回复

主要组件：
    - btw_handler: 处理 /btw <question> 命令，返回 CommandResult

使用示例：
    >>> result = await btw_handler("What is 2+2?", context)
    >>> result.message
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
    return CommandResult(message=reply, ephemeral=True)
