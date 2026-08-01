""" side_question 服务测试 """
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from illusion.engine.messages import ConversationMessage, TextBlock
from illusion.engine.query_engine import QueryEngine
from illusion.services.side_question import SideQuestionError, run_side_question


def _make_engine(messages, system_prompt="SYS", model="test-model"):
    """构造 mock QueryEngine。"""
    engine = MagicMock(spec=QueryEngine)
    engine.messages = messages
    engine.system_prompt = system_prompt
    engine.max_tokens = 4096
    engine.effort = None
    engine.tool_metadata = None
    engine.cwd = "/tmp/test"
    engine.permission_checker = MagicMock()
    # 用于验证隔离性：side_question 不应共享这些对象
    from illusion.utils.file_state_cache import FileStateCache
    engine.file_state_cache = FileStateCache()
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


@pytest.mark.asyncio
async def test_run_side_question_deny_all_tools():
    """侧问设置 deny_all_tools=True，拒绝所有工具调用。"""
    from illusion.api.client import ApiMessageCompleteEvent

    captured_context = {}

    async def fake_stream(request):
        # 验证 deny_all_tools 被设置
        captured_context["deny_all_tools"] = request._context.deny_all_tools if hasattr(request, '_context') else None
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="I cannot use tools")]),
            usage=None,
            stop_reason="end_turn",
        )

    api_client = MagicMock()
    api_client.stream_message = MagicMock(side_effect=fake_stream)
    engine = _make_engine([ConversationMessage(role="user", content=[TextBlock(text="hi")])])
    type(engine).api_client = property(lambda self: api_client)
    type(engine).model = property(lambda self: "test-model")

    # 模拟 run_query 来捕获 QueryContext
    context_captured = {}

    async def mock_run_query(context, messages):
        context_captured["deny_all_tools"] = context.deny_all_tools
        context_captured["max_turns"] = context.max_turns
        context_captured["file_state_cache_is_shared"] = context.file_state_cache is engine.file_state_cache
        # 模拟返回一个助手消息
        from illusion.engine.stream_events import AssistantTurnComplete
        yield AssistantTurnComplete(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="Answer without tools")]),
            usage=None,
        ), None

    with patch("illusion.services.side_question.run_query", side_effect=mock_run_query):
        result = await run_side_question("what is 2+2?", engine)

    # 验证 deny_all_tools=True
    assert context_captured["deny_all_tools"] is True
    # 验证 max_turns=8（允许模型在工具被拒绝后调整行为）
    assert context_captured["max_turns"] == 8
    # 验证 file_state_cache 是独立的（不共享）
    assert context_captured["file_state_cache_is_shared"] is False
    # 验证结果
    assert result == "Answer without tools"


@pytest.mark.asyncio
async def test_run_side_question_tool_attempt_returns_friendly_message():
    """模型尝试调用工具时返回友好错误提示。"""

    async def mock_run_query(context, messages):
        from illusion.engine.stream_events import (
            AssistantTurnComplete,
            ToolExecutionStarted,
        )
        # 模拟模型尝试调用工具
        yield ToolExecutionStarted(tool_name="Bash", tool_input={"command": "ls"}, tool_use_id="tool_123"), None
        yield AssistantTurnComplete(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="")]),
            usage=None,
        ), None

    with patch("illusion.services.side_question.run_query", side_effect=mock_run_query):
        engine = _make_engine([ConversationMessage(role="user", content=[TextBlock(text="hi")])])
        type(engine).api_client = property(lambda self: MagicMock())
        type(engine).model = property(lambda self: "test-model")
        result = await run_side_question("run ls", engine)

    # 验证返回友好错误提示
    assert "Bash" in result
    assert "尝试调用" in result or "instead of answering" in result.lower()


@pytest.mark.asyncio
async def test_run_side_question_state_isolation():
    """侧问使用独立的 file_state_cache，不污染主会话。"""

    captured_trackers = []

    async def mock_run_query(context, messages):
        captured_trackers.append({
            "file_state_cache": context.file_state_cache,
        })
        from illusion.engine.stream_events import AssistantTurnComplete
        yield AssistantTurnComplete(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="ok")]),
            usage=None,
        ), None

    with patch("illusion.services.side_question.run_query", side_effect=mock_run_query):
        engine = _make_engine([ConversationMessage(role="user", content=[TextBlock(text="hi")])])
        type(engine).api_client = property(lambda self: MagicMock())
        type(engine).model = property(lambda self: "test-model")
        await run_side_question("q", engine)

    # 验证使用了独立的 file_state_cache
    assert len(captured_trackers) == 1
    assert captured_trackers[0]["file_state_cache"] is not engine.file_state_cache
