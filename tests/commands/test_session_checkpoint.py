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
