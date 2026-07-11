"""引用计数工具（已废弃）
========================

.. deprecated::
    此模块已被 daemon_ipc.py 的 IPC 连接机制替代。
    新代码应使用 DaemonServer/DaemonClient 管理守护进程生命周期。
    保留此模块仅为向后兼容，不再用于生产环境。

原功能说明（仅参考）：
    为 cron 守护进程和渠道守护进程提供引用计数管理。
    多个主程序（illusion / illusion web）共享一个守护进程时，
    通过 refs 文件记录所有引用方主程序的 PID。守护进程定期自监控，
    refs 为空时自动退出。

    文件格式：每行一个 PID（纯文本，便于追加和人工检查）。

    主要函数：
        - add_ref: 追加 PID 到引用文件（去重 + 原子写）
        - remove_ref: 移除 PID（不存在时静默）
        - alive_refs: 读取并清理死 PID，返回存活列表
        - ref_monitor_loop: 异步自监控循环（守护进程使用）
"""
from __future__ import annotations

import warnings

# 模块加载时发出 DeprecationWarning
warnings.warn(
    "illusion.utils.ref_count 已被 daemon_ipc 替代，请使用 IPC 连接机制",
    DeprecationWarning,
    stacklevel=2,
)

import asyncio
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from illusion.utils.atomic_write import atomic_write_text

logger = logging.getLogger(__name__)


@contextmanager
def _file_lock(lock_path: Path) -> Iterator[None]:
    """跨平台文件锁

    Linux/macOS: fcntl.flock
    Windows: msvcrt.locking（按字节锁）

    Args:
        lock_path: 锁文件路径（与 refs 文件同目录，扩展名 .lock）
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # 以追加模式打开，确保文件存在
    f = open(lock_path, "a+")
    try:
        if os.name == "nt":
            # Windows: msvcrt.locking 按字节锁
            # 需要文件非空，先写入一个字节
            import msvcrt
            f.seek(0)
            content = f.read()
            if not content:
                f.write(".")
                f.flush()
                os.fsync(f.fileno())
            # 锁第一个字节
            while True:
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    # 被其他进程持有，重试
                    pass
            try:
                yield
            finally:
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            # Linux/macOS: fcntl.flock
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # type: ignore[attr-defined]
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
    finally:
        f.close()


def _read_pids(path: Path) -> list[int]:
    """读取 refs 文件中的 PID 列表"""
    if not path.exists():
        return []
    pids: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return pids


def _atomic_write_pids(path: Path, pids: list[int]) -> None:
    """原子写入 PID 列表"""
    content = "\n".join(str(p) for p in pids)
    if content:
        content += "\n"
    atomic_write_text(path, content)


def add_ref(refs_path: Path, pid: int) -> None:
    """追加 PID 到引用文件（去重 + 原子写）

    Args:
        refs_path: refs 文件路径
        pid: 要追加的进程 PID
    """
    lock_path = refs_path.with_suffix(refs_path.suffix + ".lock")
    with _file_lock(lock_path):
        pids = _read_pids(refs_path)
        if pid not in pids:
            pids.append(pid)
            _atomic_write_pids(refs_path, pids)


def remove_ref(refs_path: Path, pid: int) -> None:
    """移除 PID（不存在时静默）

    Args:
        refs_path: refs 文件路径
        pid: 要移除的进程 PID
    """
    lock_path = refs_path.with_suffix(refs_path.suffix + ".lock")
    with _file_lock(lock_path):
        pids = _read_pids(refs_path)
        if pid in pids:
            pids.remove(pid)
            _atomic_write_pids(refs_path, pids)


def alive_refs(refs_path: Path) -> list[int]:
    """读取并清理死 PID，返回存活 PID 列表

    Args:
        refs_path: refs 文件路径

    Returns:
        list[int]: 存活的 PID 列表
    """
    lock_path = refs_path.with_suffix(refs_path.suffix + ".lock")
    with _file_lock(lock_path):
        # 延迟导入避免与 illusion.channels.__init__ 的循环导入
        from illusion.channels.pid import is_process_alive

        pids = _read_pids(refs_path)
        alive = [p for p in pids if is_process_alive(p)]
        # 清理死 PID
        if len(alive) != len(pids):
            _atomic_write_pids(refs_path, alive)
        return alive


async def ref_monitor_loop(
    stop_event: asyncio.Event,
    refs_path: Path,
    *,
    interval: int = 30,
) -> None:
    """引用计数自监控循环

    每 interval 秒检查 refs 文件，清理死 PID。refs 为空时触发 stop_event。

    Args:
        stop_event: 停止事件（refs 为空时触发）
        refs_path: refs 文件路径
        interval: 检查间隔秒数，默认 30
    """
    while not stop_event.is_set():
        try:
            alive = alive_refs(refs_path)
            if not alive:
                logger.info("无引用方主程序，守护进程自动退出: %s", refs_path)
                stop_event.set()
                return
        except Exception:  # noqa: BLE001
            logger.debug("ref_monitor_loop 异常", exc_info=True)

        # 等待下一周期或停止信号
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            return  # stop_event 触发
        except asyncio.TimeoutError:
            pass  # 继续下一轮检查
