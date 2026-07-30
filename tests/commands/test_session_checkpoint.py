"""session 命令 checkpoint 集成测试。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from illusion.commands.session import new_handler, rewind_handler
from illusion.commands.types import CommandContext


def _make_context(tmp_path: Path, engine=None) -> CommandContext:
    """构造测试 CommandContext。"""
    return CommandContext(
        engine=engine or MagicMock(),
        cwd=str(tmp_path),
        session_id="test_sid",
    )


@pytest.mark.asyncio
async def test_new_handler_full_reset(tmp_path: Path) -> None:
    """/new 调用 full_reset 不保存当前会话。"""
    engine = MagicMock()
    engine.messages = [MagicMock()]
    ctx = _make_context(tmp_path, engine)

    result = await new_handler("", ctx)

    engine.full_reset.assert_called_once()
    assert result.reset_session is True
    assert result.clear_screen is True


@pytest.mark.asyncio
async def test_rewind_no_checkpoint(tmp_path: Path) -> None:
    """无 checkpoint 时 /rewind 返回提示。"""
    engine = MagicMock()
    engine.checkpoint_store = None
    ctx = _make_context(tmp_path, engine)

    result = await rewind_handler("1", ctx)
    assert "No checkpoint" in (result.message or "")


@pytest.mark.asyncio
async def test_rewind_code_then_both_no_misalignment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/rewind code 后 /rewind both 不应错位。

    场景：
    - 3 轮对话 + 文件修改
    - /rewind 1 code：移除第 3 轮文件快照（cp 不动）
    - 发新消息：cp=3, 新快照 cp_id=3
    - /rewind 1 both：对话移除 cp3, 文件移除 cp_id>=3
    - /rewind 1 both：对话移除 cp2, 文件无 cp_id>=2 的快照（S2 已被 code 移除）
    """
    from illusion.services.file_history import (
        FileHistoryState,
        make_snapshot,
        rewind_to,
    )

    state = FileHistoryState(session_id="abc", cwd=str(tmp_path))
    make_snapshot(state, "1", checkpoint_id=0)  # S0
    make_snapshot(state, "2", checkpoint_id=1)  # S1
    make_snapshot(state, "3", checkpoint_id=2)  # S2

    # /rewind 1 code: target_index=2, target_cp=S2.cp_id=2
    target_index = max(0, len(state.snapshots) - 1)
    target_cp_id = state.snapshots[target_index].checkpoint_id
    rewind_to(state, target_cp_id)
    assert len(state.snapshots) == 2
    assert [s.checkpoint_id for s in state.snapshots] == [0, 1]

    # 发新消息: cp=3 (假设), 新快照 cp_id=3
    make_snapshot(state, "4", checkpoint_id=3)
    assert [s.checkpoint_id for s in state.snapshots] == [0, 1, 3]

    # /rewind 1 both: target_cp = 4 - 1 = 3 (假设 next_cp=4)
    rewind_to(state, 3)
    assert [s.checkpoint_id for s in state.snapshots] == [0, 1]

    # /rewind 1 both: target_cp = 3 - 1 = 2 (假设 next_cp=3)
    # 无 cp_id >= 2 的快照（S2 已被 code 移除），不恢复文件
    changed = rewind_to(state, 2)
    assert changed == []
    assert [s.checkpoint_id for s in state.snapshots] == [0, 1]
