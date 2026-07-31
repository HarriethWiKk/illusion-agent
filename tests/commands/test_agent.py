""" /agent 命令处理器测试 """
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from illusion.commands.agent import agent_handler
from illusion.commands.types import CommandContext
from illusion.engine.messages import ConversationMessage, ToolResultBlock, ToolUseBlock
from illusion.tasks.types import TaskRecord


def _ctx(engine_messages=None):
    engine = MagicMock()
    engine.messages = engine_messages or []
    return CommandContext(engine=engine, cwd="."), engine


@pytest.mark.asyncio
async def test_agent_no_args_returns_list_hint():
    ctx, _ = _ctx()
    result = await agent_handler("", ctx)
    assert result.message is not None


@pytest.mark.asyncio
async def test_agent_create_returns_hint():
    ctx, _ = _ctx()
    result = await agent_handler("create", ctx)
    assert "create" in (result.message or "").lower() or result.message is not None


@pytest.mark.asyncio
async def test_agent_foreground_returns_tool_result():
    """前台 agent：<id> 为 tool_use_id，从 transcript 返回 tool_result 内容。"""
    tool_use_id = "toolu_abc123"
    messages = [
        ConversationMessage(role="assistant", content=[
            ToolUseBlock(id=tool_use_id, name="agent", input={"name": "test-runner"}),
        ]),
        ConversationMessage(role="user", content=[
            ToolResultBlock(tool_use_id=tool_use_id, content="前台 agent 的最终回复"),
        ]),
    ]
    ctx, _ = _ctx(messages)
    result = await agent_handler(tool_use_id, ctx)
    assert result.message == "前台 agent 的最终回复"


@pytest.mark.asyncio
async def test_agent_background_returns_task_output(monkeypatch):
    """后台 agent：<id> 为 task_id，从 TaskRecord 读取。"""
    record = TaskRecord(
        id="agent_xyz",
        type="in_process_agent",
        status="completed",
        description="bg agent",
        cwd=".",
        output_file=Path("/tmp/o.log"),
    )
    record.result = "后台 agent 的最终回复"
    manager = MagicMock()
    manager._tasks = {"agent_xyz": record}
    manager.read_task_output = MagicMock(return_value="后台 agent 的最终回复")
    monkeypatch.setattr("illusion.commands.agent.get_task_manager", lambda: manager)

    ctx, _ = _ctx([])
    result = await agent_handler("agent_xyz", ctx)
    assert result.message == "后台 agent 的最终回复"


@pytest.mark.asyncio
async def test_agent_unknown_id_returns_not_found():
    ctx, _ = _ctx([])
    # 不在前台 transcript，也不在 TaskRecord
    manager = MagicMock()
    manager._tasks = {}
    # 注意：agent.py 中 get_task_manager 是模块级导入，需 patch 对应路径
    # 但本测试 engine.messages 为空，前台查找失败后才查后台
    # 需要 mock get_task_manager 返回空 manager
    import illusion.commands.agent as agent_mod
    original = agent_mod.get_task_manager
    agent_mod.get_task_manager = lambda: manager
    try:
        result = await agent_handler("nonexistent", ctx)
    finally:
        agent_mod.get_task_manager = original
    assert "not found" in (result.message or "").lower() or "No task" in (result.message or "")
