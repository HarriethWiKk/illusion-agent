"""CheckpointStore 单元测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from illusion.engine.messages import ConversationMessage
from illusion.services.checkpoint_store import CheckpointStore


@pytest.fixture
def store(tmp_path: Path) -> CheckpointStore:
    """构造临时 CheckpointStore。"""
    session_dir = tmp_path / "sess-abc"
    session_dir.mkdir()
    return CheckpointStore(session_dir, "abc")


@pytest.mark.asyncio
async def test_append_and_restore_basic(store: CheckpointStore) -> None:
    """append 后 restore 能重建所有状态（含缓存分项）。"""
    cid = await store.append_checkpoint()
    assert cid == 0
    user_msg = ConversationMessage.from_user_text("hello")
    await store.append_message(user_msg)
    await store.append_usage(
        input_tokens=100, output_tokens=5,
        cache_read_input_tokens=1000, cache_creation_input_tokens=200,
    )

    result = await store.restore()
    assert len(result.messages) == 1
    assert result.messages[0].text == "hello"
    assert result.usage_input == 100
    assert result.usage_output == 5
    assert result.usage_cache_read == 1000
    assert result.usage_cache_creation == 200
    assert result.checkpoint_count == 1


@pytest.mark.asyncio
async def test_last_usage_roundtrip(store: CheckpointStore) -> None:
    """_usage 行的单次分项在 restore 后可恢复（用于 rewind/resume 后 StatusBar）。"""
    from illusion.api.usage import UsageSnapshot

    await store.append_checkpoint()  # id=0
    await store.append_message(ConversationMessage.from_user_text("hi"))
    last = UsageSnapshot(
        input_tokens=617,
        output_tokens=170,
        cache_read_input_tokens=34400,
        cache_creation_input_tokens=0,
    )
    await store.append_usage(
        input_tokens=35017,
        output_tokens=170,
        cache_read_input_tokens=34400,
        cache_creation_input_tokens=0,
        last_usage=last,
        last_message_count=3,
    )

    result = await store.restore()
    assert result.last_usage is not None
    assert result.last_usage.input_tokens == 617
    assert result.last_usage.output_tokens == 170
    assert result.last_usage.cache_read_input_tokens == 34400
    assert result.last_usage_message_count == 3


@pytest.mark.asyncio
async def test_rewind_restores_last_usage_before_target(store: CheckpointStore) -> None:
    """rewind 后恢复目标点之前的最后一次单次用量。"""
    from illusion.api.usage import UsageSnapshot

    # turn 0
    await store.append_checkpoint()  # id=0
    await store.append_message(ConversationMessage.from_user_text("turn0"))
    await store.append_usage(
        100, 5, last_usage=UsageSnapshot(input_tokens=100, output_tokens=5), last_message_count=2
    )
    # turn 1
    await store.append_checkpoint()  # id=1
    await store.append_message(ConversationMessage.from_user_text("turn1"))
    await store.append_usage(
        200, 10, last_usage=UsageSnapshot(input_tokens=100, output_tokens=5, cache_read_input_tokens=100), last_message_count=4
    )

    # rewind 到 id=1 之前 → 保留 turn0 的 _usage（单次 input=100, output=5）
    result = await store.rewind_to(1)
    assert result.last_usage is not None
    assert result.last_usage.input_tokens == 100
    assert result.last_usage.output_tokens == 5
    assert result.last_usage_message_count == 2
    # 累积值也回到 turn0 的
    assert result.usage_input == 100


@pytest.mark.asyncio
async def test_rewind_to_target_checkpoint(store: CheckpointStore) -> None:
    """rewind_to 截断目标 checkpoint 及之后内容。"""
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
    await store.append_checkpoint()  # id=0
    await store.append_message(ConversationMessage.from_user_text("msg"))
    await store.append_usage(100, 5)

    result = await store.rewind_to(0)
    assert result.checkpoint_count == 0
    assert len(result.messages) == 0
    assert result.usage_input == 0


@pytest.mark.asyncio
async def test_restore_empty_store(tmp_path: Path) -> None:
    """空 store restore 返回默认值。"""
    session_dir = tmp_path / "empty"
    session_dir.mkdir()
    s = CheckpointStore(session_dir, "empty")
    result = await s.restore()
    assert result.messages == []
    assert result.usage_input == 0
    assert result.usage_cache_read == 0
    assert result.usage_cache_creation == 0


@pytest.mark.asyncio
async def test_truncate_all(store: CheckpointStore) -> None:
    """truncate_all 清空文件。"""
    await store.append_checkpoint()
    await store.append_message(ConversationMessage.from_user_text("x"))
    assert store._file.exists()
    await store.truncate_all()
    assert not store._file.exists()
    assert store.next_checkpoint_id == 0


@pytest.mark.asyncio
async def test_lazy_dir_creation(tmp_path: Path) -> None:
    """构造 CheckpointStore 时不创建目录，第一次 append 时才创建。"""
    session_dir = tmp_path / "lazy-sess"
    assert not session_dir.exists()
    store = CheckpointStore(session_dir, "lazy")
    # 构造后目录仍不存在
    assert not session_dir.exists()
    # 第一次 append 触发延迟创建
    await store.append_checkpoint()
    assert session_dir.exists()
    assert (session_dir / "context.jsonl").exists()


@pytest.mark.asyncio
async def test_lazy_dir_not_created_on_restore(tmp_path: Path) -> None:
    """restore 不触发延迟创建（目录不存在时返回空结果）。"""
    session_dir = tmp_path / "no-create"
    store = CheckpointStore(session_dir, "nope")
    result = await store.restore()
    assert result.messages == []
    # restore 后目录仍不应被创建
    assert not session_dir.exists()


@pytest.mark.asyncio
async def test_legacy_system_prompt_line_ignored(tmp_path: Path) -> None:
    """旧文件中的 _system_prompt / _system_overhead 行被忽略，不影响 restore。"""
    session_dir = tmp_path / "legacy"
    session_dir.mkdir()
    store = CheckpointStore(session_dir, "legacy")
    # 手动写入旧格式行（含 _system_prompt / _system_overhead）
    import json
    (session_dir / "context.jsonl").write_text(
        json.dumps({"role": "_system_prompt", "content": "old", "hash": "h1"}) + "\n"
        + json.dumps({"role": "_checkpoint", "id": 0}) + "\n"
        + json.dumps({"role": "user", "message": ConversationMessage.from_user_text("hi").model_dump(mode="json")}) + "\n"
        + json.dumps({"role": "_system_overhead", "tokens": 500, "prompt_hash": "h1"}) + "\n",
        encoding="utf-8",
    )
    result = await store.restore()
    assert len(result.messages) == 1
    assert result.messages[0].text == "hi"
    assert result.usage_cache_read == 0
    assert result.checkpoint_count == 1
