# src/illusion/services/cron_spawn.py
"""cron 守护进程 spawn 逻辑

通过 DaemonClient/DaemonServer 管理 IPC 连接，替代 PID 文件 + refs 文件。
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from illusion.config.paths import get_cron_dir, get_logs_dir
from illusion.services.cron import load_cron_jobs

if TYPE_CHECKING:
    from illusion.daemon_ipc import DaemonClient

logger = logging.getLogger(__name__)


def _cleanup_old_pid_files(cron_dir: Path) -> None:
    """清理旧版 PID/refs 文件（一次性迁移）"""
    for name in ("scheduler.pid", "scheduler.refs", "scheduler.refs.lock"):
        try:
            (cron_dir / name).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


def maybe_spawn_cron_daemon() -> tuple[subprocess.Popen[bytes] | None, "DaemonClient | None"]:
    """主程序启动时自动拉起 cron 守护进程

    通过 DaemonClient 尝试连接 IPC。连接成功则持有 client 作为引用；
    连接失败则 spawn 子进程，轮询连接成功后持有 client。

    Returns:
        tuple: (Popen 实例或 None, DaemonClient 实例或 None)
    """
    from illusion.daemon_ipc import DaemonClient, DaemonType, connect_and_register

    jobs = load_cron_jobs()
    enabled = [j for j in jobs if j.get("enabled")]
    if not enabled:
        return None, None

    cron_dir = get_cron_dir()
    client = DaemonClient(daemon_type=DaemonType.CRON, pid=os.getpid())

    # 尝试连接已运行的守护进程（connect+register 在同一事件循环中完成）
    connected, _ = connect_and_register(client)

    if connected:
        # 守护进程已在运行，持有连接作为引用
        return None, client

    # 连接失败：清理旧文件并 spawn 新守护进程
    _cleanup_old_pid_files(cron_dir)

    creation_flags = 0
    if os.name == "nt":
        creation_flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    logs_dir = get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "cron_scheduler.log"

    try:
        daemon_cwd = str(Path.cwd())
    except (OSError, FileNotFoundError):
        daemon_cwd = str(cron_dir)

    try:
        log_file = open(log_path, "ab")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.Popen(
            [sys.executable, "-m", "illusion", "cron", "serve"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creation_flags,
            close_fds=True,
            env=env,
            cwd=daemon_cwd,
        )
    except OSError as exc:
        logger.warning("启动 cron 守护进程失败: %s", exc)
        return None, None

    # 轮询连接（每次 connect+register 在独立事件循环中完成，最多 10s，每 0.5s 重试）
    import time
    connected = False
    for _ in range(20):
        client = DaemonClient(daemon_type=DaemonType.CRON, pid=os.getpid())
        ok, _ = connect_and_register(client)
        if ok:
            connected = True
            break
        time.sleep(0.5)

    if not connected:
        logger.warning("cron 守护进程 spawn 后 10s 内未能连接")
        return proc, None

    return proc, client


def kill_cron_daemon_by_pid() -> bool:
    """通过 IPC 停止 cron 守护进程

    通过 DaemonClient 连接守护进程，发送 ping 获取 daemon_pid，
    然后终止该进程。成功后清理 IPC 残留文件。

    Returns:
        bool: 成功终止返回 True，无运行中的守护进程返回 False
    """
    import asyncio
    from illusion.daemon_ipc import DaemonClient, DaemonType

    client = DaemonClient(daemon_type=DaemonType.CRON, pid=os.getpid())

    loop = asyncio.new_event_loop()
    try:
        connected = loop.run_until_complete(client.connect())
        if not connected:
            return False

        pong = loop.run_until_complete(client.ping(timeout=2.0))
        if pong is None or "daemon_pid" not in pong:
            loop.run_until_complete(client.close())
            return False

        daemon_pid = pong["daemon_pid"]
        loop.run_until_complete(client.close())
    finally:
        loop.close()

    # 终止守护进程
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(daemon_pid)],
                capture_output=True,
                check=False,
            )
        else:
            import signal
            try:
                os.killpg(os.getpgid(daemon_pid), signal.SIGTERM)  # type: ignore[attr-defined]
            except (ProcessLookupError, PermissionError):
                pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("停止 cron 守护进程失败: %s", exc)
        return False

    # 清理 IPC 残留文件（Unix socket）
    cron_dir = get_cron_dir()
    if os.name != "nt":
        try:
            (cron_dir / "cron_daemon.sock").unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass

    logger.info("Stopped cron daemon (pid=%d)", daemon_pid)
    return True
