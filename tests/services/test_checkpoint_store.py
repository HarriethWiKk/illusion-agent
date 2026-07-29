"""CheckpointStore 单元测试。"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from illusion.engine.messages import ConversationMessage
from illusion.services.checkpoint_store import CheckpointStore, RestoreResult


@pytest.fixture
def store(tmp_path: Path) -> CheckpointStore:
    """构造临时 CheckpointStore。"""
    session_dir = tmp_path / "sess-abc"
    session_dir.mkdir()
    return CheckpointStore(session_dir, "abc")


@pytest.mark.asyncio
async def test_append_and_restore_basic(store: CheckpointStore) -> None:
    """append 后 restore 能重建所有状态。"""
    await store.append_system_prompt("You are assistant.", "hash1")
    cid = await store.append_checkpoint()
    assert cid == 0
    user_msg = ConversationMessage.from_user_text("hello")
    await store.append_message(user_msg)
    await store.append_usage(input_tokens=100, output_tokens=5)
    await store.append_system_overhead(tokens=2000, prompt_hash="hash1")

    result = await store.restore()
    assert len(result.messages) == 1
    assert result.messages[0].text == "hello"
    assert result.usage_input == 100
    assert result.usage_output == 5
    assert result.system_overhead == 2000
    assert result.system_overhead_hash == "hash1"
    assert result.system_prompt == "You are assistant."
    assert result.system_prompt_hash == "hash1"
    assert result.checkpoint_count == 1


@pytest.mark.asyncio
async def test_rewind_to_target_checkpoint(store: CheckpointStore) -> None:
    """rewind_to 截断目标 checkpoint 及之后内容。"""
    await store.append_system_prompt("sys", "h1")
    # turn 0
    await store.append_checkpoint()  # id=0
    await store.append_message(ConversationMessage.from_user_text("turn0"))
    await store.append_usage(100, 5)
    # turn 1
    await store.append_checkpoint()  # id=1
    await store.append_message(ConversationMessage.from_user_text("turn1"))
    await store.append_usage(200, 10)
    # turn 2
    await store.append_checkpoint()  # id=2
    await store.append_message(ConversationMessage.from_user_text("turn2"))
    await store.append_usage(300, 15)

    assert store.next_checkpoint_id == 3
    # rewind 到 id=1 之前（保留 id=0 的 turn 0）
    result = await store.rewind_to(1)
    assert result.checkpoint_count == 1
    assert len(result.messages) == 1
    assert result.messages[0].text == "turn0"
    assert result.usage_input == 100
    assert result.usage_output == 5
    assert store.next_checkpoint_id == 1


@pytest.mark.asyncio
async def test_rewind_to_first_checkpoint(store: CheckpointStore) -> None:
    """rewind_to(0) 清空所有 checkpoint 之后内容。"""
    await store.append_system_prompt("sys", "h1")
    await store.append_checkpoint()  # id=0
    await store.append_message(ConversationMessage.from_user_text("msg"))
    await store.append_usage(100, 5)

    result = await store.rewind_to(0)
    assert result.checkpoint_count == 0
    assert len(result.messages) == 0
    assert result.usage_input == 0
    assert result.system_prompt == "sys"  # _system_prompt 在 checkpoint 之前，保留


@pytest.mark.asyncio
async def test_restore_empty_store(tmp_path: Path) -> None:
    """空 store restore 返回默认值。"""
    session_dir = tmp_path / "empty"
    session_dir.mkdir()
    s = CheckpointStore(session_dir, "empty")
    result = await s.restore()
    assert result.messages == []
    assert result.usage_input == 0
    assert result.system_overhead is None


@pytest.mark.asyncio
async def test_system_prompt_last_write_wins(store: CheckpointStore) -> None:
    """多次 append_system_prompt 后 restore 取最后一个。"""
    await store.append_system_prompt("v1", "h1")
    await store.append_system_prompt("v2", "h2")
    result = await store.restore()
    assert result.system_prompt == "v2"
    assert result.system_prompt_hash == "h2"


@pytest.mark.asyncio
async def test_truncate_all(store: CheckpointStore) -> None:
    """truncate_all 清空文件。"""
    await store.append_checkpoint()
    await store.append_message(ConversationMessage.from_user_text("x"))
    assert store._file.exists()
    await store.truncate_all()
    assert not store._file.exists()
    assert store.next_checkpoint_id == 0
