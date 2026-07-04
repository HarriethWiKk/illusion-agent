"""cron 守护进程 spawn 逻辑测试"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from illusion.services.cron_spawn import (
    kill_cron_daemon_by_pid,
    maybe_spawn_cron_daemon,
)


@pytest.fixture(autouse=True)
def _tmp_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """重定向 cron 目录和日志目录到临时目录"""
    cron_dir = tmp_path / "data" / "cron"
    logs_dir = tmp_path / "logs"
    cron_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "illusion.services.cron_spawn.get_cron_dir", lambda: cron_dir
    )
    monkeypatch.setattr(
        "illusion.services.cron_spawn.get_logs_dir", lambda: logs_dir
    )


def test_no_enabled_jobs_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """无启用任务时返回 None"""
    monkeypatch.setattr(
        "illusion.services.cron_spawn.load_cron_jobs", lambda: []
    )
    proc = maybe_spawn_cron_daemon()
    assert proc is None


def test_no_jobs_at_all_returns_none(monkeypatch: pytest.MonkeyPatch):
    """任务列表为空时返回 None"""
    monkeypatch.setattr(
        "illusion.services.cron_spawn.load_cron_jobs", lambda: []
    )
    proc = maybe_spawn_cron_daemon()
    assert proc is None


def test_disabled_jobs_return_none(monkeypatch: pytest.MonkeyPatch):
    """所有任务禁用时返回 None"""
    monkeypatch.setattr(
        "illusion.services.cron_spawn.load_cron_jobs",
        lambda: [{"name": "j1", "enabled": False}],
    )
    proc = maybe_spawn_cron_daemon()
    assert proc is None


def test_pid_running_adds_ref(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """守护进程已在运行时追加引用并返回 None"""
    monkeypatch.setattr(
        "illusion.services.cron_spawn.load_cron_jobs",
        lambda: [{"name": "j1", "enabled": True}],
    )

    # 模拟 PID 文件指向存活进程
    current_pid = os.getpid()
    pid_path = tmp_path / "data" / "cron" / "scheduler.pid"
    pid_path.write_text(str(current_pid), encoding="utf-8")

    # PidFile.is_running 返回 True
    def _fake_is_running(self):
        return True
    monkeypatch.setattr(
        "illusion.channels.pid.PidFile.is_running", _fake_is_running
    )

    # 追踪 add_ref 调用
    add_ref_calls: list[int] = []
    def _fake_add_ref(path, pid):
        add_ref_calls.append(pid)
    monkeypatch.setattr(
        "illusion.services.cron_spawn.add_ref", _fake_add_ref
    )

    proc = maybe_spawn_cron_daemon()
    assert proc is None
    assert current_pid in add_ref_calls


def test_kill_no_pid_returns_false(monkeypatch: pytest.MonkeyPatch):
    """kill_cron_daemon_by_pid 无 PID 文件时返回 False"""
    # PidFile.is_running 返回 False
    def _fake_is_running(self):
        return False
    monkeypatch.setattr(
        "illusion.channels.pid.PidFile.is_running", _fake_is_running
    )

    result = kill_cron_daemon_by_pid()
    assert result is False
