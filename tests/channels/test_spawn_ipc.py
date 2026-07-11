# tests/channels/test_spawn_ipc.py
"""渠道守护进程 IPC spawn 测试"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from illusion.channels import maybe_spawn_channel_daemon


@pytest.fixture(autouse=True)
def _tmp_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """重定向渠道数据目录"""
    data_dir = tmp_path / "channels_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "illusion.config.paths.get_channels_data_dir", lambda: data_dir
    )
    # patch 在 channels/__init__ 模块的引用（若不存在则不报错，仅做额外保险）
    monkeypatch.setattr(
        "illusion.channels.get_channels_data_dir", lambda: data_dir, raising=False
    )


def test_daemon_running_connects_client(monkeypatch: pytest.MonkeyPatch):
    """守护进程已运行时：连接成功，持有 DaemonClient"""
    from illusion.channels.config import ChannelsConfig, FeishuChannelConfig
    cfg = ChannelsConfig(feishu=FeishuChannelConfig(enabled=True, app_id="x", app_secret="y"))
    monkeypatch.setattr("illusion.channels.load_channels_config", lambda: cfg)

    async def _fake_connect(self):
        self._conn = object()  # 模拟真实 connect 设置 _conn
        return True
    monkeypatch.setattr("illusion.daemon_ipc.DaemonClient.connect", _fake_connect)

    async def _fake_register(self):
        return {"type": "ok"}
    monkeypatch.setattr("illusion.daemon_ipc.DaemonClient.register", _fake_register)

    proc, ref = maybe_spawn_channel_daemon()
    assert proc is None
    assert ref is not None
    # ref 内部应持有已连接的 client
    assert ref._client is not None
    assert ref._client.is_connected


def test_fingerprint_mismatch_triggers_restart(monkeypatch: pytest.MonkeyPatch):
    """指纹不匹配时返回 restart_required，杀旧进程并 spawn 新的"""
    from illusion.channels.config import ChannelsConfig, FeishuChannelConfig
    cfg = ChannelsConfig(feishu=FeishuChannelConfig(enabled=True, app_id="x", app_secret="y"))
    monkeypatch.setattr("illusion.channels.load_channels_config", lambda: cfg)

    async def _fake_connect(self):
        self._conn = object()
        return True
    monkeypatch.setattr("illusion.daemon_ipc.DaemonClient.connect", _fake_connect)

    async def _fake_register(self):
        # 返回 daemon_pid 以触发杀旧进程路径
        return {"type": "restart_required", "daemon_pid": 99999}
    monkeypatch.setattr("illusion.daemon_ipc.DaemonClient.register", _fake_register)

    # 跟踪杀旧进程调用（Unix 用 os.kill；Windows 用 ctypes OpenProcess，PID 不存在返回 0）
    kill_called: list[bool] = []
    if os.name != "nt":
        def _track_kill(pid, sig):
            kill_called.append(True)
            raise ProcessLookupError(f"测试 mock: PID {pid} 不存在")
        monkeypatch.setattr("os.kill", _track_kill)

    # 跟踪 subprocess.Popen 调用
    spawn_calls: list[list[str]] = []

    class _FakeProc:
        pid = 99999

    def _fake_popen(*args, **kwargs):
        spawn_calls.append(args[0] if args else [])
        return _FakeProc()
    monkeypatch.setattr("subprocess.Popen", _fake_popen)

    proc, client = maybe_spawn_channel_daemon()
    # 验证 spawn 发生（指纹不匹配时应 spawn 新进程）
    assert proc is not None, "指纹不匹配时应 spawn 新进程"
    assert len(spawn_calls) >= 1, "应调用 subprocess.Popen 至少一次"
    # 验证杀旧进程被尝试（Unix 下可跟踪 os.kill；Windows 下 ctypes 路径也会执行但不抛异常）
    if os.name != "nt":
        assert kill_called, "指纹不匹配时应尝试杀旧进程"
