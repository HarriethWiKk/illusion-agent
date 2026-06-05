"""Cron 调度器单元测试。

测试对齐 openclaw 设计后的调度器功能：
- 历史记录、到期任务判断、任务执行、调度器循环
- 新增：错误退避、独立会话执行、CronScheduler 类
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from illusion.services.cron_scheduler import (
    CronScheduler,
    _get_backoff_seconds,
    _jobs_due,
    append_history,
    execute_job,
    load_history,
)


@pytest.fixture(autouse=True)
def _tmp_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """将数据和日志目录重定向到临时目录。"""
    data_dir = tmp_path / "data"
    logs_dir = tmp_path / "logs"
    cron_dir = tmp_path / "data" / "cron"
    data_dir.mkdir()
    logs_dir.mkdir()
    cron_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("illusion.services.cron_scheduler.get_cron_dir", lambda: cron_dir)
    monkeypatch.setattr("illusion.services.cron_scheduler.get_logs_dir", lambda: logs_dir)
    # 同时重定向 cron 注册表
    monkeypatch.setattr(
        "illusion.services.cron.get_cron_registry_path",
        lambda: cron_dir / "jobs.json",
    )


class TestHistory:
    """历史记录测试。"""

    def test_empty_history(self) -> None:
        assert load_history() == []

    def test_append_and_load(self) -> None:
        append_history({"name": "j1", "status": "success"})
        append_history({"name": "j2", "status": "failed"})
        entries = load_history()
        assert len(entries) == 2
        assert entries[0]["name"] == "j1"

    def test_filter_by_name(self) -> None:
        append_history({"name": "j1", "status": "success"})
        append_history({"name": "j2", "status": "success"})
        entries = load_history(job_name="j1")
        assert len(entries) == 1
        assert entries[0]["name"] == "j1"

    def test_filter_by_id(self) -> None:
        append_history({"id": "abc", "name": "j1", "status": "success"})
        append_history({"id": "def", "name": "j2", "status": "success"})
        entries = load_history(job_id="abc")
        assert len(entries) == 1
        assert entries[0]["id"] == "abc"

    def test_limit(self) -> None:
        for i in range(10):
            append_history({"name": f"j{i}", "status": "success"})
        entries = load_history(limit=3)
        assert len(entries) == 3
        # 应该是最后 3 条
        assert entries[0]["name"] == "j7"


class TestBackoff:
    """错误退避策略测试。"""

    def test_no_backoff_on_zero_errors(self) -> None:
        assert _get_backoff_seconds(0) == 0

    def test_backoff_increases(self) -> None:
        assert _get_backoff_seconds(1) == 30
        assert _get_backoff_seconds(2) == 60
        assert _get_backoff_seconds(3) == 300
        assert _get_backoff_seconds(4) == 900
        assert _get_backoff_seconds(5) == 3600

    def test_backoff_caps_at_max(self) -> None:
        """超出退避序列时应使用最大值。"""
        assert _get_backoff_seconds(100) == 3600


class TestJobsDue:
    """到期任务判断测试。"""

    def test_due_job(self) -> None:
        now = datetime.now()
        past = (now - timedelta(minutes=5)).isoformat()
        jobs = [
            {"name": "j1", "schedule": "* * * * *", "enabled": True, "next_run": past},
        ]
        due = _jobs_due(jobs, now)
        assert len(due) == 1

    def test_future_job_not_due(self) -> None:
        now = datetime.now()
        future = (now + timedelta(hours=1)).isoformat()
        jobs = [
            {"name": "j1", "schedule": "* * * * *", "enabled": True, "next_run": future},
        ]
        due = _jobs_due(jobs, now)
        assert len(due) == 0

    def test_disabled_job_not_due(self) -> None:
        now = datetime.now()
        past = (now - timedelta(minutes=5)).isoformat()
        jobs = [
            {"name": "j1", "schedule": "* * * * *", "enabled": False, "next_run": past},
        ]
        due = _jobs_due(jobs, now)
        assert len(due) == 0

    def test_invalid_schedule_skipped(self) -> None:
        now = datetime.now()
        past = (now - timedelta(minutes=5)).isoformat()
        jobs = [
            {"name": "j1", "schedule": "not valid", "enabled": True, "next_run": past},
        ]
        due = _jobs_due(jobs, now)
        assert len(due) == 0

    def test_missing_next_run_skipped(self) -> None:
        now = datetime.now()
        jobs = [
            {"name": "j1", "schedule": "* * * * *", "enabled": True},
        ]
        due = _jobs_due(jobs, now)
        assert len(due) == 0

    def test_job_in_backoff_period_skipped(self) -> None:
        """连续错误的任务在退避期内应被跳过。"""
        now = datetime.now()
        past = (now - timedelta(minutes=5)).isoformat()
        recent = (now - timedelta(seconds=10)).isoformat()
        jobs = [
            {
                "name": "j1",
                "schedule": "* * * * *",
                "enabled": True,
                "next_run": past,
                "consecutive_errors": 3,
                "last_run": recent,
            },
        ]
        due = _jobs_due(jobs, now)
        assert len(due) == 0

    def test_job_after_backoff_period_is_due(self) -> None:
        """退避期结束后任务应恢复执行。"""
        now = datetime.now()
        past = (now - timedelta(minutes=5)).isoformat()
        old = (now - timedelta(hours=1)).isoformat()
        jobs = [
            {
                "name": "j1",
                "schedule": "* * * * *",
                "enabled": True,
                "next_run": past,
                "consecutive_errors": 1,
                "last_run": old,
            },
        ]
        due = _jobs_due(jobs, now)
        assert len(due) == 1


class TestExecuteJob:
    """任务执行测试。"""

    @pytest.mark.asyncio
    async def test_missing_prompt(self, tmp_path: Path) -> None:
        """缺少 prompt 的任务应返回错误。"""
        job = {"name": "no-prompt", "id": "test1", "cwd": str(tmp_path)}
        entry = await execute_job(job)
        assert entry["status"] == "error"
        assert "prompt" in entry["stderr"]

    @pytest.mark.asyncio
    async def test_execute_calls_subprocess(self, tmp_path: Path) -> None:
        """应通过子进程执行 prompt。"""
        mock_result = {
            "returncode": 0,
            "status": "success",
            "stdout": "OK",
            "stderr": "",
        }
        with patch(
            "illusion.services.cron_scheduler._execute_prompt_in_subprocess",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_exec:
            job = {"name": "test", "id": "test1", "prompt": "echo hello", "cwd": str(tmp_path)}
            entry = await execute_job(job)
            assert entry["status"] == "success"
            mock_exec.assert_called_once_with("echo hello", tmp_path, timeout=300)


class TestSchedulerClass:
    """CronScheduler 类测试。"""

    @pytest.mark.asyncio
    async def test_start_and_stop(self) -> None:
        """调度器应能正常启动和停止。"""
        scheduler = CronScheduler()
        assert not scheduler.is_running

        await scheduler.start()
        assert scheduler.is_running

        await scheduler.stop()
        assert not scheduler.is_running

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self) -> None:
        """重复启动不应出错。"""
        scheduler = CronScheduler()
        await scheduler.start()
        await scheduler.start()  # 不应抛出异常
        assert scheduler.is_running
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_status(self) -> None:
        """状态查询应返回正确信息。"""
        scheduler = CronScheduler()
        status = scheduler.status()
        assert "running" in status
        assert "total_jobs" in status
        assert "enabled_jobs" in status
