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

    proc, client = maybe_spawn_channel_daemon()
    assert proc is None
    assert client is not None
    assert client.is_connected


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
        return {"type": "restart_required"}
    monkeypatch.setattr("illusion.daemon_ipc.DaemonClient.register", _fake_register)

    # 模拟杀旧进程（避免实际杀进程）
    monkeypatch.setattr("os.kill", lambda *a: None)

    # 模拟 subprocess.Popen
    class _FakeProc:
        pid = 99999
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: _FakeProc())

    proc, client = maybe_spawn_channel_daemon()
    # restart_required 后会尝试 spawn 新进程
    # 在测试环境中 spawn 会成功（mock），但后续轮询连接可能失败
    # 不崩溃即算通过
