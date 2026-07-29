"""QueryEngine 与 CheckpointStore 集成测试。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from illusion.engine.messages import ConversationMessage
from illusion.engine.query_engine import QueryEngine


def _make_engine(tmp_path: Path) -> QueryEngine:
    """构造测试用 QueryEngine（不调用真实 API）。"""
    return QueryEngine(
        api_client=MagicMock(),
        tool_registry=MagicMock(),
        permission_checker=MagicMock(),
        cwd=tmp_path,
        model="test-model",
        system_prompt="sys",
    )


@pytest.mark.asyncio
async def test_submit_message_appends_checkpoint(tmp_path: Path, monkeypatch) -> None:
    """submit_message 入口 append checkpoint + user message。"""
    from illusion.services.checkpoint_store import CheckpointStore

    engine = _make_engine(tmp_path)
    store = CheckpointStore(tmp_path / "sess", "abc")
    engine.set_checkpoint_store(store)
    engine.set_system_prompt("sys")

    # mock run_query 返回空事件流（使用 monkeypatch 自动还原，避免污染后续测试）
    import illusion.engine.query_engine as qe_mod
    async def _fake_run_query(ctx, msgs):
        if False:
            yield  # 让函数成为 async generator（不 yield 任何东西）
    monkeypatch.setattr(qe_mod, "run_query", _fake_run_query)

    async for _ in engine.submit_message("hello"):
        pass

    result = await store.restore()
    assert result.checkpoint_count == 1
    assert len(result.messages) >= 1
    assert result.messages[0].text == "hello"


@pytest.mark.asyncio
async def test_submit_message_persists_assistant_and_tool_messages(
    tmp_path: Path, monkeypatch
) -> None:
    """run_query 内部 append 的 assistant/tool 消息必须持久化到 CheckpointStore。

    回归测试：修复前 submit_message 只持久化 user message，run_query 内部
    append 的 assistant 回复和 tool 结果消息丢失，导致 resume 后对话历史缺失。
    """
    from illusion.services.checkpoint_store import CheckpointStore

    engine = _make_engine(tmp_path)
    store = CheckpointStore(tmp_path / "sess", "abc")
    engine.set_checkpoint_store(store)
    engine.set_system_prompt("sys")

    # mock run_query：模拟内部 append assistant + tool result 消息
    import illusion.engine.query_engine as qe_mod
    from illusion.engine.messages import TextBlock
    from illusion.engine.stream_events import AssistantTurnComplete
    from illusion.api.usage import UsageSnapshot

    async def _fake_run_query(ctx, msgs):
        # 模拟 query.py 内部行为：append assistant 消息到 msgs（即 self._messages）
        assistant_msg = ConversationMessage(
            role="assistant",
            content=[TextBlock(type="text", text="你好！我是助手。")],
        )
        msgs.append(assistant_msg)
        # 模拟 append tool result user 消息
        tool_result_msg = ConversationMessage(
            role="user",
            content=[TextBlock(type="text", text="[tool_result] ok")],
        )
        msgs.append(tool_result_msg)
        yield AssistantTurnComplete(message=assistant_msg, usage=None), None

    monkeypatch.setattr(qe_mod, "run_query", _fake_run_query)

    async for _ in engine.submit_message("你好"):
        pass

    result = await store.restore()
    # 应该有 3 条消息：user(你好) + assistant(回复) + user(tool_result)
    assert len(result.messages) == 3
    assert result.messages[0].role == "user"
    assert result.messages[0].text == "你好"
    assert result.messages[1].role == "assistant"
    assert result.messages[1].text == "你好！我是助手。"
    assert result.messages[2].role == "user"
    assert result.messages[2].text == "[tool_result] ok"


@pytest.mark.asyncio
async def test_continue_pending_persists_assistant_messages(
    tmp_path: Path, monkeypatch
) -> None:
    """continue_pending 同样必须持久化 run_query 内部 append 的消息。"""
    from illusion.services.checkpoint_store import CheckpointStore
    from illusion.engine.messages import TextBlock
    from illusion.engine.stream_events import AssistantTurnComplete

    engine = _make_engine(tmp_path)
    store = CheckpointStore(tmp_path / "sess", "abc")
    engine.set_checkpoint_store(store)
    engine.set_system_prompt("sys")

    # 预置一条待续的 user message（含 tool_result）模拟中断恢复场景
    engine._messages.append(ConversationMessage.from_user_text("继续"))
    await store.append_message(engine._messages[-1])

    import illusion.engine.query_engine as qe_mod

    async def _fake_run_query(ctx, msgs):
        assistant_msg = ConversationMessage(
            role="assistant",
            content=[TextBlock(type="text", text="已继续执行")],
        )
        msgs.append(assistant_msg)
        yield AssistantTurnComplete(message=assistant_msg, usage=None), None

    monkeypatch.setattr(qe_mod, "run_query", _fake_run_query)

    async for _ in engine.continue_pending():
        pass

    result = await store.restore()
    # 应该有 2 条消息：user(继续) + assistant(已继续执行)
    assert len(result.messages) == 2
    assert result.messages[0].role == "user"
    assert result.messages[0].text == "继续"
    assert result.messages[1].role == "assistant"
    assert result.messages[1].text == "已继续执行"


def test_full_reset_clears_all_state(tmp_path: Path) -> None:
    """full_reset 清空所有状态。"""
    engine = _make_engine(tmp_path)
    engine._messages.append(ConversationMessage.from_user_text("x"))
    engine._session_id = "old"
    engine.full_reset()
    assert engine.messages == []
    assert engine._session_id == ""
    assert engine._checkpoint_store is None


def test_set_session_id(tmp_path: Path) -> None:
    """set_session_id 更新内部 session_id。"""
    engine = _make_engine(tmp_path)
    engine.set_session_id("new_sid")
    assert engine._session_id == "new_sid"
