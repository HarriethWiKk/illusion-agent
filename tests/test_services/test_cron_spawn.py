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
    proc, client = maybe_spawn_cron_daemon()
    assert proc is None
    assert client is None


def test_no_jobs_at_all_returns_none(monkeypatch: pytest.MonkeyPatch):
    """任务列表为空时返回 None"""
    monkeypatch.setattr(
        "illusion.services.cron_spawn.load_cron_jobs", lambda: []
    )
    proc, client = maybe_spawn_cron_daemon()
    assert proc is None
    assert client is None


def test_disabled_jobs_return_none(monkeypatch: pytest.MonkeyPatch):
    """所有任务禁用时返回 None"""
    monkeypatch.setattr(
        "illusion.services.cron_spawn.load_cron_jobs",
        lambda: [{"name": "j1", "enabled": False}],
    )
    proc, client = maybe_spawn_cron_daemon()
    assert proc is None
    assert client is None


def test_daemon_running_connects_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """守护进程已在运行时：连接成功，持有 DaemonClient，返回 None"""
    monkeypatch.setattr(
        "illusion.services.cron_spawn.load_cron_jobs",
        lambda: [{"name": "j1", "enabled": True}],
    )

    # 模拟 DaemonClient.connect 返回 True（同时设置 _conn 使 is_connected 为 True）
    async def _fake_connect(self):
        self._conn = object()  # 任何非 None 值即可让 is_connected 返回 True
        return True
    monkeypatch.setattr("illusion.daemon_ipc.DaemonClient.connect", _fake_connect)

    # 模拟 DaemonClient.register 返回 {"type": "ok"}（注意：必须返回 dict，不是 bool）
    async def _fake_register(self):
        return {"type": "ok"}
    monkeypatch.setattr("illusion.daemon_ipc.DaemonClient.register", _fake_register)

    proc, ref = maybe_spawn_cron_daemon()
    assert proc is None
    assert ref is not None
    # ref 内部应持有已连接的 client
    assert ref._client is not None
    assert ref._client.is_connected


def test_no_daemon_running_spawns_and_connects(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """守护进程未运行时：spawn 子进程，后台线程异步连接"""
    monkeypatch.setattr(
        "illusion.services.cron_spawn.load_cron_jobs",
        lambda: [{"name": "j1", "enabled": True}],
    )

    # DaemonClient.connect 第一次返回 False（未启动），之后返回 True
    call_count = {"n": 0}
    async def _fake_connect(self):
        call_count["n"] += 1
        if call_count["n"] > 1:
            self._conn = object()  # 模拟连接已建立
            return True
        return False

    async def _fake_register(self):
        return {"type": "ok"}

    monkeypatch.setattr("illusion.daemon_ipc.DaemonClient.connect", _fake_connect)
    monkeypatch.setattr("illusion.daemon_ipc.DaemonClient.register", _fake_register)

    # 模拟 subprocess.Popen
    class _FakeProc:
        pid = 99999

    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: _FakeProc())

    proc, ref = maybe_spawn_cron_daemon()
    assert proc is not None
    assert ref is not None
    # 后台线程异步连接：等待最多 2s 让 ref._client 被设置
    import time
    for _ in range(40):
        if ref._client is not None:
            break
        time.sleep(0.05)
    assert ref._client is not None, "后台线程应在 2s 内完成连接"
    assert ref._client.is_connected
