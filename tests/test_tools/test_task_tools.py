"""Tests for task tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from illusion.tasks import get_task_manager
from illusion.tools.base import ToolExecutionContext
from illusion.tools.task_create_tool import TaskCreateTool, TaskCreateToolInput
from illusion.tools.task_get_tool import TaskGetTool, TaskGetToolInput
from illusion.tools.task_list_tool import TaskListTool, TaskListToolInput
from illusion.tools.task_output_tool import TaskOutputTool, TaskOutputToolInput
from illusion.tools.task_update_tool import TaskUpdateTool, TaskUpdateToolInput


@pytest.mark.asyncio
async def test_task_create_and_output_tool(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    context = ToolExecutionContext(cwd=tmp_path)

    create_result = await TaskCreateTool().execute(
        TaskCreateToolInput(
            subject="echo",
            description="echo task",
        ),
        context,
    )
    assert create_result.is_error is False
    task_id = create_result.output.split()[2]

    output_result = await TaskOutputTool().execute(
        TaskOutputToolInput(task_id=task_id),
        context,
    )
    assert output_result.output == "(no output)"


@pytest.mark.asyncio
async def test_task_update_tool_updates_metadata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    context = ToolExecutionContext(cwd=tmp_path)

    create_result = await TaskCreateTool().execute(
        TaskCreateToolInput(
            subject="updatable",
            description="updatable task",
        ),
        context,
    )
    task_id = create_result.output.split()[2]

    update_result = await TaskUpdateTool().execute(
        TaskUpdateToolInput(
            task_id=task_id,
            progress=60,
            status_note="waiting on verification",
            description="renamed task",
        ),
        context,
    )
    assert update_result.is_error is False

    task = get_task_manager().get_task(task_id)
    assert task is not None
    assert task.description == "renamed task"
    assert task.metadata.get("progress") == "60"
    assert task.metadata.get("status_note") == "waiting on verification"


@pytest.mark.asyncio
async def test_task_update_tool_missing_id_is_soft_ignored(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    context = ToolExecutionContext(cwd=tmp_path)

    result = await TaskUpdateTool().execute(
        TaskUpdateToolInput(
            task_id="td18fe38b",
            progress=10,
        ),
        context,
    )
    assert result.is_error is False
    assert "Ignored stale task_update" in result.output


@pytest.mark.asyncio
async def test_task_status_roundtrip_uses_in_progress_for_tool_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    context = ToolExecutionContext(cwd=tmp_path)

    create_result = await TaskCreateTool().execute(
        TaskCreateToolInput(
            subject="status roundtrip",
            description="status roundtrip task",
        ),
        context,
    )
    task_id = create_result.output.split()[2]

    update_result = await TaskUpdateTool().execute(
        TaskUpdateToolInput(task_id=task_id, status="in_progress"),
        context,
    )
    assert "status=in_progress" in update_result.output

    task = get_task_manager().get_task(task_id)
    assert task is not None
    assert task.status == "running"

    get_result = await TaskGetTool().execute(
        TaskGetToolInput(task_id=task_id),
        context,
    )
    assert "status: in_progress" in get_result.output

    list_result = await TaskListTool().execute(TaskListToolInput(), context)
    assert f"id={task_id} status=in_progress" in list_result.output
