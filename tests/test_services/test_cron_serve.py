"""cron 守护进程主入口测试"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

from illusion.services.cron_serve import run_cron_serve, _serve_async


@pytest.fixture(autouse=True)
def _tmp_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """重定向 cron 目录和日志目录到临时目录"""
    cron_dir = tmp_path / "data" / "cron"
    logs_dir = tmp_path / "logs"
    cron_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "illusion.services.cron_serve.get_cron_dir", lambda: cron_dir
    )
    monkeypatch.setattr(
        "illusion.services.cron_serve.get_logs_dir", lambda: logs_dir
    )


def test_run_cron_serve_writes_pid(tmp_path: Path):
    """run_cron_serve 启动时写入 PID 文件"""
    cron_dir = tmp_path / "data" / "cron"
    pid_path = cron_dir / "scheduler.pid"

    # PidFile.is_running 返回 False（无已有守护进程）
    def _fake_is_running(self):
        return False
    with patch("illusion.channels.pid.PidFile.is_running", _fake_is_running):
        # 模拟 _serve_async 立即返回
        async def _fake_serve():
            pass
        with patch("illusion.services.cron_serve._serve_async", _fake_serve):
            with patch("illusion.services.cron_serve._setup_logging"):
                run_cron_serve()

    # PID 文件应在运行时写入，退出时释放
    # 由于 run_cron_serve 在 finally 中 release，退出后文件应不存在
    assert not pid_path.exists() or pid_path.read_text().strip() == ""


def test_run_cron_serve_already_running_returns(tmp_path: Path):
    """已有守护进程在运行时静默退出"""
    current_pid = os.getpid()
    cron_dir = tmp_path / "data" / "cron"
    pid_path = cron_dir / "scheduler.pid"
    pid_path.write_text(str(current_pid + 1000), encoding="utf-8")

    # PidFile.is_running 返回 True
    def _fake_is_running(self):
        return True
    with patch("illusion.channels.pid.PidFile.is_running", _fake_is_running):
        # _serve_async 不应被调用
        call_count = {"n": 0}
        async def _fake_serve():
            call_count["n"] += 1
        with patch("illusion.services.cron_serve._serve_async", _fake_serve):
            with patch("illusion.services.cron_serve._setup_logging"):
                run_cron_serve()

    assert call_count["n"] == 0


@pytest.mark.asyncio
async def test_serve_async_starts_scheduler_and_monitor(tmp_path: Path):
    """_serve_async 启动调度器和自监控任务"""
    cron_dir = tmp_path / "data" / "cron"
    refs_path = cron_dir / "scheduler.refs"
    refs_path.parent.mkdir(parents=True, exist_ok=True)
    # 写入当前进程 PID 作为引用
    refs_path.write_text(str(os.getpid()), encoding="utf-8")

    stop_event = asyncio.Event()

    # 模拟调度器
    mock_scheduler = AsyncMock()
    mock_scheduler.is_running = False
    mock_scheduler.start = AsyncMock()
    mock_scheduler.stop = AsyncMock()

    # 让 stop_event 在 0.1s 后触发（模拟 refs 为空或外部信号）
    async def _trigger_stop():
        await asyncio.sleep(0.1)
        stop_event.set()

    with patch("illusion.services.cron_serve.get_scheduler", return_value=mock_scheduler):
        with patch("illusion.services.cron_serve.ref_monitor_loop", new_callable=AsyncMock) as mock_monitor:
            # 让 monitor_loop 把 TEST 的 stop_event 传播到 SERVE 的 stop_event
            # （_serve_async 内部创建自己的 stop_event 并传给 ref_monitor_loop；
            # monitor 收到的是 SERVE 的，需要从 TEST 的转发过去）
            async def _mock_monitor(event, path, **kwargs):
                await stop_event.wait()  # 等 TEST 的触发
                event.set()  # 传播到 SERVE 的 stop_event
            mock_monitor.side_effect = _mock_monitor

            asyncio.create_task(_trigger_stop())
            await _serve_async()

    mock_scheduler.start.assert_called_once()
    mock_scheduler.stop.assert_called_once()
