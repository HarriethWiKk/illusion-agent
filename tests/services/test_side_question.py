""" side_question 服务测试 """
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from illusion.engine.messages import ConversationMessage, TextBlock
from illusion.engine.query_engine import QueryEngine
from illusion.services.side_question import SideQuestionError, run_side_question


def _make_engine(messages, system_prompt="SYS", model="test-model"):
    """构造 mock QueryEngine。"""
    engine = MagicMock(spec=QueryEngine)
    engine.messages = messages
    engine.system_prompt = system_prompt
    return engine


@pytest.mark.asyncio
async def test_run_side_question_returns_text():
    """侧问返回 LLM 文本回复。"""
    from illusion.api.client import ApiMessageCompleteEvent, ApiTextDeltaEvent

    async def fake_stream(request):
        yield ApiTextDeltaEvent(text="Hello ")
        yield ApiTextDeltaEvent(text="world")
        yield ApiMessageCompleteEvent(message=ConversationMessage(role="assistant", content=[TextBlock(text="Hello world")]), usage=None, stop_reason="end_turn")

    api_client = MagicMock()
    api_client.stream_message = MagicMock(side_effect=fake_stream)
    engine = _make_engine([ConversationMessage(role="user", content=[TextBlock(text="hi")])])
    type(engine).api_client = property(lambda self: api_client)
    type(engine).model = property(lambda self: "test-model")
    type(engine).max_tokens = property(lambda self: 4096)

    result = await run_side_question("what is 1+1?", engine)
    assert result == "Hello world"


@pytest.mark.asyncio
async def test_run_side_question_strips_unfinished_assistant():
    """剥离末尾未完成 assistant 消息。"""
    from illusion.api.client import ApiMessageCompleteEvent, ApiTextDeltaEvent

    captured = {}

    async def fake_stream(request):
        captured["messages"] = list(request.messages)
        yield ApiTextDeltaEvent(text="ok")
        yield ApiMessageCompleteEvent(message=ConversationMessage(role="assistant", content=[TextBlock(text="ok")]), usage=None, stop_reason="end_turn")

    api_client = MagicMock()
    api_client.stream_message = MagicMock(side_effect=fake_stream)
    msgs = [
        ConversationMessage(role="user", content=[TextBlock(text="hi")]),
        ConversationMessage(role="assistant", content=[TextBlock(text="partial")]),
    ]
    engine = _make_engine(msgs)
    type(engine).api_client = property(lambda self: api_client)
    type(engine).model = property(lambda self: "test-model")
    type(engine).max_tokens = property(lambda self: 4096)

    await run_side_question("q", engine)
    roles = [m.role for m in captured["messages"]]
    assert roles == ["user", "user"]


@pytest.mark.asyncio
async def test_run_side_question_error_raises():
    """API 异常抛出 SideQuestionError。"""
    api_client = MagicMock()
    api_client.stream_message = MagicMock(side_effect=RuntimeError("boom"))
    engine = _make_engine([ConversationMessage(role="user", content=[TextBlock(text="hi")])])
    type(engine).api_client = property(lambda self: api_client)
    type(engine).model = property(lambda self: "test-model")
    type(engine).max_tokens = property(lambda self: 4096)

    with pytest.raises(SideQuestionError):
        await run_side_question("q", engine)
