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
    assert "creation" in (result.message or "").lower() or "wizard" in (result.message or "").lower()


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
async def test_agent_unknown_id_returns_not_found(monkeypatch):
    ctx, _ = _ctx([])
    # 不在前台 transcript，也不在 TaskRecord
    manager = MagicMock()
    manager._tasks = {}
    monkeypatch.setattr("illusion.commands.agent.get_task_manager", lambda: manager)
    result = await agent_handler("nonexistent", ctx)
    assert "not found" in (result.message or "").lower() or "No task" in (result.message or "")


@pytest.mark.asyncio
async def test_agent_foreground_empty_tool_result():
    """前台 agent：tool_result 内容为空，返回 'Agent tool result ... is empty.' 提示。"""
    tool_use_id = "toolu_empty"
    messages = [
        ConversationMessage(role="user", content=[
            ToolResultBlock(tool_use_id=tool_use_id, content=""),
        ]),
    ]
    ctx, _ = _ctx(messages)
    result = await agent_handler(tool_use_id, ctx)
    assert result.message == f"Agent tool result '{tool_use_id}' is empty."


@pytest.mark.asyncio
async def test_agent_background_wrong_type_returns_not_agent(monkeypatch):
    """后台 agent：TaskRecord.type 非 agent 类型，返回 'Task ... is not an agent task.'。"""
    record = TaskRecord(
        id="bash_task",
        type="local_bash",
        status="completed",
        description="bash task",
        cwd=".",
        output_file=Path("/tmp/o.log"),
    )
    manager = MagicMock()
    manager._tasks = {"bash_task": record}
    monkeypatch.setattr("illusion.commands.agent.get_task_manager", lambda: manager)

    ctx, _ = _ctx([])
    result = await agent_handler("bash_task", ctx)
    assert result.message == "Task 'bash_task' is not an agent task."


@pytest.mark.asyncio
async def test_agent_background_not_completed_returns_status(monkeypatch):
    """后台 agent：status 非 completed，返回 'Agent ... is not completed (status: ...).'。"""
    record = TaskRecord(
        id="agent_running",
        type="in_process_agent",
        status="running",
        description="running agent",
        cwd=".",
        output_file=Path("/tmp/o.log"),
    )
    manager = MagicMock()
    manager._tasks = {"agent_running": record}
    monkeypatch.setattr("illusion.commands.agent.get_task_manager", lambda: manager)

    ctx, _ = _ctx([])
    result = await agent_handler("agent_running", ctx)
    assert result.message == "Agent 'agent_running' is not completed (status: running)."


@pytest.mark.asyncio
async def test_agent_background_read_output_value_error_returns_str(monkeypatch):
    """后台 agent：read_task_output 抛 ValueError，返回 str(exc)。"""
    record = TaskRecord(
        id="agent_err",
        type="in_process_agent",
        status="completed",
        description="agent with missing output",
        cwd=".",
        output_file=Path("/tmp/missing.log"),
    )
    manager = MagicMock()
    manager._tasks = {"agent_err": record}
    manager.read_task_output = MagicMock(side_effect=ValueError("task not found"))
    monkeypatch.setattr("illusion.commands.agent.get_task_manager", lambda: manager)

    ctx, _ = _ctx([])
    result = await agent_handler("agent_err", ctx)
    assert result.message == "task not found"


@pytest.mark.asyncio
async def test_agent_background_empty_output_returns_hint(monkeypatch):
    """后台 agent：read_task_output 返回空字符串，返回 'Agent ... has no captured output.'。"""
    record = TaskRecord(
        id="agent_empty",
        type="in_process_agent",
        status="completed",
        description="agent with empty output",
        cwd=".",
        output_file=Path("/tmp/empty.log"),
    )
    manager = MagicMock()
    manager._tasks = {"agent_empty": record}
    manager.read_task_output = MagicMock(return_value="")
    monkeypatch.setattr("illusion.commands.agent.get_task_manager", lambda: manager)

    ctx, _ = _ctx([])
    result = await agent_handler("agent_empty", ctx)
    assert result.message == "Agent 'agent_empty' has no captured output."
