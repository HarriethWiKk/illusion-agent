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
