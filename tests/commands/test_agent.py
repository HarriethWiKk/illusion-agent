""" /agent 命令处理器测试 """
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from illusion.commands.agent import agent_handler
from illusion.commands.types import CommandContext
from illusion.tasks.types import TaskRecord


def _ctx():
    engine = MagicMock()
    return CommandContext(engine=engine, cwd="."), engine


@pytest.mark.asyncio
async def test_agent_no_args_returns_hint():
    ctx, _ = _ctx()
    result = await agent_handler("", ctx)
    assert result.message is not None


@pytest.mark.asyncio
async def test_agent_create_returns_hint():
    ctx, _ = _ctx()
    result = await agent_handler("create", ctx)
    assert result.message is not None


@pytest.mark.asyncio
async def test_agent_task_id_returns_summary(monkeypatch):
    ctx, _ = _ctx()
    record = TaskRecord(
        id="t1",
        type="in_process_agent",
        status="completed",
        description="d",
        cwd=".",
        output_file=Path("/tmp/o"),
    )
    record.summary = "the summary text"
    manager = MagicMock()
    manager._tasks = {"t1": record}
    monkeypatch.setattr("illusion.commands.agent.get_task_manager", lambda: manager)
    result = await agent_handler("t1", ctx)
    assert "the summary text" in (result.message or "")


@pytest.mark.asyncio
async def test_agent_task_id_not_found(monkeypatch):
    ctx, _ = _ctx()
    manager = MagicMock()
    manager._tasks = {}
    monkeypatch.setattr("illusion.commands.agent.get_task_manager", lambda: manager)
    result = await agent_handler("nonexistent", ctx)
    assert result.message is not None
    assert "nonexistent" in (result.message or "") or "not found" in (result.message or "").lower()
