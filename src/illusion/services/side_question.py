""" 一次性侧问服务

在不打断主对话的前提下发起单轮 LLM 查询，复用 QueryEngine 当前上下文
（系统提示词 + 消息历史），但不写入 engine.messages、不触发 hooks、不带工具。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from illusion.api.client import ApiMessageRequest
from illusion.engine.messages import ConversationMessage, TextBlock

if TYPE_CHECKING:
    from illusion.engine.query_engine import QueryEngine
    from illusion.state import AppStateStore

logger = logging.getLogger(__name__)


class SideQuestionError(Exception):
    """侧问查询失败。"""


async def run_side_question(
    question: str,
    engine: "QueryEngine",
    app_state: "AppStateStore | None" = None,
) -> str:
    """发起一次性侧问，返回纯文本回复。

    Args:
        question: 用户的侧问内容
        engine: 当前会话的 QueryEngine（只读访问其 messages 与 system_prompt）
        app_state: 应用状态（保留参数，当前未使用）

    Returns:
        str: LLM 的纯文本回复

    Raises:
        SideQuestionError: LLM 查询失败时抛出
    """
    del app_state  # 预留
    # 复制当前消息并剥离末尾未完成的 assistant 消息
    messages = list(engine.messages)
    while messages and messages[-1].role == "assistant":
        messages.pop()

    # 追加本次侧问作为 user 消息
    messages.append(ConversationMessage.from_user_text(question))

    request = ApiMessageRequest(
        model=engine.model,
        messages=messages,
        system_prompt=engine.system_prompt or None,
        max_tokens=engine.max_tokens,
        tools=[],
        effort=None,
    )

    try:
        chunks: list[str] = []
        async for event in engine.api_client.stream_message(request):
            text = getattr(event, "text", None)
            if text:
                chunks.append(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[side_question] 查询失败: %s", exc)
        raise SideQuestionError(str(exc)) from exc

    return "".join(chunks).strip()
