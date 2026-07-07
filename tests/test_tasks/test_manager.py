"""Tests for background task management."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from illusion.tasks.manager import BackgroundTaskManager, get_task_manager


@pytest.mark.asyncio
async def test_create_shell_task_and_read_output(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()

    task = await manager.create_shell_task(
        command="printf 'hello task'",
        description="hello",
        cwd=tmp_path,
    )

    await asyncio.wait_for(manager._waiters[task.id], timeout=5)  # type: ignore[attr-defined]
    updated = manager.get_task(task.id)
    assert updated is not None
    assert updated.status == "completed"
    assert "hello task" in manager.read_task_output(task.id)


@pytest.mark.asyncio
async def test_create_agent_task_with_command_override_and_write(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()

    task = await manager.create_agent_task(
        prompt="first",
        description="agent",
        cwd=tmp_path,
        command="while read line; do echo \"got:$line\"; break; done",
    )

    await asyncio.wait_for(manager._waiters[task.id], timeout=5)  # type: ignore[attr-defined]
    assert "got:first" in manager.read_task_output(task.id)


@pytest.mark.asyncio
async def test_write_to_stopped_agent_task_restarts_process(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()

    task = await manager.create_agent_task(
        prompt="ready",
        description="agent",
        cwd=tmp_path,
        command="while read line; do echo \"got:$line\"; break; done",
    )
    await asyncio.wait_for(manager._waiters[task.id], timeout=5)  # type: ignore[attr-defined]

    await manager.write_to_task(task.id, "follow-up")
    await asyncio.wait_for(manager._waiters[task.id], timeout=5)  # type: ignore[attr-defined]

    output = manager.read_task_output(task.id)
    assert "got:ready" in output
    assert "got:follow-up" in output
    updated = manager.get_task(task.id)
    assert updated is not None
    assert updated.metadata["restart_count"] == "1"


@pytest.mark.asyncio
async def test_stop_task(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()

    task = await manager.create_shell_task(
        command="sleep 30",
        description="sleeper",
        cwd=tmp_path,
    )
    await manager.stop_task(task.id)
    updated = manager.get_task(task.id)
    assert updated is not None
    assert updated.status == "killed"


def test_get_task_manager_keeps_managers_per_task_list(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ILLUSION_TASK_LIST_ID", raising=False)

    default_manager = get_task_manager()
    default_task = default_manager.create_pending_task(
        subject="default",
        description="default task",
    )

    monkeypatch.setenv("ILLUSION_TASK_LIST_ID", "team-alpha")
    team_manager = get_task_manager()
    assert team_manager is not default_manager
    assert team_manager.get_task(default_task.id) is None

    monkeypatch.delenv("ILLUSION_TASK_LIST_ID", raising=False)
    restored_default_manager = get_task_manager()
    assert restored_default_manager is default_manager
    assert restored_default_manager.get_task(default_task.id) is not None


@pytest.mark.asyncio
async def test_on_task_complete_callback_invoked_on_process_exit(tmp_path, monkeypatch):
    """子进程退出时 on_task_complete 回调应被调用，传入正确的 task_id 和最终 task 记录。"""
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()
    completed_calls: list[tuple[str, str, str]] = []  # (task_id, status, type)

    def _on_complete(task_id: str, task):
        completed_calls.append((task_id, task.status, task.type))

    manager.on_task_complete = _on_complete

    record = await manager.create_shell_task(
        description="callback test",
        cwd=str(tmp_path),
        command="exit 0",
    )
    # 等待 watcher 完成
    import asyncio
    await asyncio.wait_for(manager._waiters[record.id], timeout=5)  # type: ignore[attr-defined]

    assert len(completed_calls) == 1
    assert completed_calls[0][0] == record.id
    assert completed_calls[0][1] == "completed"
    assert completed_calls[0][2] == "local_bash"


@pytest.mark.asyncio
async def test_on_task_complete_none_does_not_crash(tmp_path, monkeypatch):
    """on_task_complete 为 None 时不应崩溃。"""
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    manager = BackgroundTaskManager()
    # on_task_complete 默认 None
    assert manager.on_task_complete is None

    record = await manager.create_shell_task(
        description="no callback test",
        cwd=str(tmp_path),
        command="printf 'ok'",
    )
    import asyncio
    await asyncio.wait_for(manager._waiters[record.id], timeout=5)  # type: ignore[attr-defined]
    # 不崩溃即通过
    task = manager.get_task(record.id)
    assert task is not None
