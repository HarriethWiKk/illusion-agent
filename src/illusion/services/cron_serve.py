"""cron 守护进程主入口
====================

实现 'illusion cron serve' 命令：启动 CronScheduler 后台循环，
监控引用计数，refs 为空时自动退出。

函数说明：
    - run_cron_serve: serve 命令主入口
    - _serve_async: 异步主循环
    - _setup_logging: 配置日志
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Any

from illusion.channels.pid import PidFile, read_pid
from illusion.config.paths import get_cron_dir, get_logs_dir
from illusion.services.cron_scheduler import get_scheduler
from illusion.utils.ref_count import ref_monitor_loop

logger = logging.getLogger(__name__)

# 监控间隔（与调度器 tick 一致）
_MONITOR_INTERVAL_SECONDS = 30


def _setup_logging() -> None:
    """配置日志：RotatingFileHandler + StreamHandler"""
    from logging.handlers import RotatingFileHandler

    log_path = get_logs_dir() / "cron_scheduler.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
    )

    # 文件 handler（10MB × 5 备份）
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # stdout handler（logging 已在模块顶部导入，直接用 logging.StreamHandler）
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    logger.info("cron 守护进程启动，日志文件: %s", log_path)


def run_cron_serve() -> None:
    """cron 守护进程主入口

    启动 CronScheduler 异步循环，监控 scheduler.refs。
    refs 为空时自动退出。
    """
    cron_dir = get_cron_dir()
    pid_file = PidFile(cron_dir / "scheduler.pid")

    # 竞态检查：已有守护进程在运行则退出
    if pid_file.is_running():
        existing_pid = read_pid(pid_file.path) or 0
        if existing_pid != os.getpid():
            logger.debug(
                "Cron daemon already running (pid=%d), exiting", existing_pid
            )
            return

    _setup_logging()

    # 写入 PID
    try:
        pid_file.acquire(os.getpid())
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入 scheduler.pid 失败: %s", exc)

    try:
        asyncio.run(_serve_async())
    except KeyboardInterrupt:
        pass
    finally:
        try:
            pid_file.release()
        except Exception:  # noqa: BLE001
            pass


async def _serve_async() -> None:
    """异步主循环：调度任务 + 自监控"""
    cron_dir = get_cron_dir()
    refs_path = cron_dir / "scheduler.refs"

    scheduler = get_scheduler()
    stop_event = asyncio.Event()

    # 信号处理
    loop = asyncio.get_event_loop()

    def _on_signal(*_: Any) -> None:
        stop_event.set()

    try:
        loop.add_signal_handler(signal.SIGINT, _on_signal)
        loop.add_signal_handler(signal.SIGTERM, _on_signal)
    except (NotImplementedError, RuntimeError, AttributeError):
        # Windows 不支持 add_signal_handler，依赖 KeyboardInterrupt
        pass

    # 启动调度器
    await scheduler.start()

    # 启动自监控任务
    monitor_task = asyncio.create_task(
        ref_monitor_loop(
            stop_event,
            refs_path,
            interval=_MONITOR_INTERVAL_SECONDS,
        ),
        name="cron-ref-monitor",
    )

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass

    # 优雅关闭
    monitor_task.cancel()
    await scheduler.stop()
    await asyncio.gather(monitor_task, return_exceptions=True)
