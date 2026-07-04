"""cron 守护进程 spawn 管理
========================

主程序启动时自动拉起 cron 守护进程，使用引用计数支持多实例共享。

主要函数：
    - maybe_spawn_cron_daemon: 主程序启动时调用，有启用任务则 spawn
    - kill_cron_daemon_by_pid: 通过 PID 文件停止守护进程

使用示例：
    >>> from illusion.services.cron_spawn import maybe_spawn_cron_daemon
    >>> proc = maybe_spawn_cron_daemon()
    >>> if proc:
    ...     print(f"Started cron daemon (pid={proc.pid})")
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from illusion.channels.pid import PidFile, read_pid
from illusion.config.paths import get_cron_dir, get_logs_dir
from illusion.services.cron import load_cron_jobs
from illusion.utils.ref_count import add_ref

logger = logging.getLogger(__name__)


def maybe_spawn_cron_daemon() -> subprocess.Popen[bytes] | None:
    """主程序启动时自动拉起 cron 守护进程

    读取 jobs.json，若有启用任务且守护进程未运行则 spawn 子进程。
    守护进程已在运行时追加自己 PID 到 scheduler.refs。

    Returns:
        subprocess.Popen 实例（spawn 了新进程）或 None（未 spawn）
    """
    jobs = load_cron_jobs()
    if not any(j.get("enabled", True) for j in jobs):
        return None  # 无启用任务，跳过

    cron_dir = get_cron_dir()
    pid_file = PidFile(cron_dir / "scheduler.pid")
    refs_path = cron_dir / "scheduler.refs"

    if pid_file.is_running():
        # 守护进程已在运行：追加自己 PID 到 refs
        add_ref(refs_path, os.getpid())
        logger.debug("Cron daemon already running, added ref pid=%d", os.getpid())
        return None

    # spawn 子进程
    creation_flags = 0
    if os.name == "nt":
        # Windows: DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        creation_flags = 0x00000008 | 0x00000200

    log_path = get_logs_dir() / "cron_scheduler.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # daemon 的 cwd：优先用主进程 cwd，失效时回退到 cron_dir
    try:
        daemon_cwd = str(Path.cwd())
    except (OSError, FileNotFoundError):
        daemon_cwd = str(cron_dir)

    try:
        log_file = open(log_path, "ab")  # noqa: SIM115  追加写
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
        pid_file.acquire(proc.pid)
        add_ref(refs_path, os.getpid())  # spawn 方也加引用
        logger.info("Started cron daemon (pid=%d)", proc.pid)
        return proc
    except OSError as exc:
        logger.warning("启动 cron 守护进程失败: %s", exc)
        return None


def kill_cron_daemon_by_pid() -> bool:
    """通过 PID 文件停止 cron 守护进程

    不依赖 proc 引用，通过 scheduler.pid 读取 PID 后终止进程。
    成功后清理 PID 文件和 refs 文件。

    Returns:
        bool: 成功终止返回 True，无运行中的守护进程返回 False
    """
    cron_dir = get_cron_dir()
    pid_file = PidFile(cron_dir / "scheduler.pid")
    if not pid_file.is_running():
        return False

    old_pid = read_pid(pid_file.path)
    if old_pid is None:
        return False

    try:
        if os.name == "nt":
            # Windows: taskkill /T /F 终止整个进程树
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(old_pid)],
                capture_output=True,
                check=False,
            )
        else:
            # Unix: 发送 SIGTERM 到进程组
            import signal
            try:
                os.killpg(os.getpgid(old_pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("停止 cron 守护进程失败: %s", exc)
        return False

    # 清理 PID 和 refs 文件
    pid_file.release()
    refs_path = cron_dir / "scheduler.refs"
    try:
        refs_path.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass

    logger.info("Stopped cron daemon (pid=%d)", old_pid)
    return True
