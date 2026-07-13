# src/illusion/services/cron_serve.py
"""cron 守护进程主入口

实现 'illusion cron serve' 命令：启动 CronScheduler 后台循环，
通过 DaemonServer 监控 IPC 连接数，连接归零时自动退出。
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from illusion.config.paths import get_cron_dir, get_logs_dir
from illusion.services.cron_scheduler import get_scheduler

logger = logging.getLogger(__name__)


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

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    logger.info("cron 守护进程启动，日志文件: %s", log_path)


def run_cron_serve() -> None:
    """cron 守护进程主入口（IPC 版）

    启动 DaemonServer 监听连接，运行 _serve_async 等待连接归零。
    """
    from illusion.daemon_ipc import DaemonServer, DaemonType
    from illusion.services.cron_spawn import _cleanup_old_pid_files

    cron_dir = get_cron_dir()
    _cleanup_old_pid_files(cron_dir)

    _setup_logging()

    server = DaemonServer(
        daemon_type=DaemonType.CRON,
        daemon_pid=os.getpid(),
    )

    loop: asyncio.AbstractEventLoop | None = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.start())
        loop.run_until_complete(_serve_async(server))
    except KeyboardInterrupt:
        pass
    finally:
        if loop is not None:
            loop.run_until_complete(server.stop())
            loop.close()


async def _serve_async(server: Any) -> None:
    """异步主循环：启动调度器 + 等待连接归零

    Args:
        server: DaemonServer 实例
    """
    scheduler = get_scheduler()
    stop_event = asyncio.Event()

    # 启动调度器
    await scheduler.start()

    # 启动连接监控
    async def _monitor() -> None:
        await server.wait_for_no_connections(grace_seconds=3.0)
        stop_event.set()

    monitor_task = asyncio.create_task(_monitor(), name="cron-connection-monitor")
    stop_wait_task = asyncio.create_task(stop_event.wait())

    try:
        # 同时等待 stop_event 或 monitor_task 完成
        # monitor 异常时需要传播，使 _serve_async 退出
        done, _ = await asyncio.wait(
            [stop_wait_task, monitor_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        # monitor 异常结束时传播异常
        if monitor_task in done and not monitor_task.cancelled():
            exc = monitor_task.exception()
            if exc is not None:
                raise exc
    finally:
        monitor_task.cancel()
        stop_wait_task.cancel()
        for t in (monitor_task, stop_wait_task):
            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                logger.warning("cron serve 等待 task 完成时捕获异常: %s", exc, exc_info=exc)
        await scheduler.stop()
