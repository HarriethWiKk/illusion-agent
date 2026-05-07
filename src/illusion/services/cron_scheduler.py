"""
Cron 调度器模块
===============

对齐 openclaw 的定时任务调度模式：非阻塞、独立会话执行。

核心设计：
    - 调度器作为后台 asyncio 任务运行，不阻塞当前会话
    - 每个到期任务在独立子进程中执行（通过 illusion -p 启动）
    - 使用本地时间进行调度判断
    - 支持错误退避和连续错误跟踪
    - 跨平台兼容（Windows / Linux / macOS）

主要组件：
    - CronScheduler: 调度器类，管理后台调度循环
    - append_history / load_history: 执行历史记录
    - scheduler_status: 调度器状态查询
    - ensure_started: 确保调度器正在运行（创建任务时自动调用）

使用示例：
    >>> from illusion.services.cron_scheduler import get_scheduler, ensure_started
    >>> await ensure_started()      # 确保调度器运行
    >>> scheduler = get_scheduler()
    >>> scheduler.is_running        # 检查状态
    >>> await scheduler.stop()      # 停止调度
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from illusion.config.paths import get_data_dir, get_logs_dir
from illusion.services.cron import (
    load_cron_jobs,
    mark_job_run,
    remove_expired_jobs,
    validate_cron_expression,
)

# 模块级日志记录器
logger = logging.getLogger(__name__)

# 调度周期间隔（秒）- 每 30 秒检查一次到期任务
TICK_INTERVAL_SECONDS = 30
"""调度器检查到期任务的频率（秒）。"""

# 错误退避策略（秒）：连续错误后逐渐增加等待时间
# 对齐 openclaw DEFAULT_ERROR_BACKOFF_SCHEDULE_MS
_ERROR_BACKOFF_SECONDS = [30, 60, 300, 900, 3600]
"""错误退避时间序列（秒），按连续错误次数索引。"""

# 任务执行超时（秒）
_JOB_TIMEOUT_SECONDS = 300
"""单个任务的执行超时时间（秒），默认 5 分钟。"""

# 最大并发任务数
_MAX_CONCURRENT_JOBS = 1
"""同时执行的最大任务数，对齐 openclaw maxConcurrentRuns。"""


# ---------------------------------------------------------------------------
# 历史记录
# ---------------------------------------------------------------------------

def get_history_path() -> Path:
    """返回 Cron 执行历史记录文件路径。"""
    return get_data_dir() / "cron_history.jsonl"


def append_history(entry: dict[str, Any]) -> None:
    """向历史日志追加一条执行记录。

    每条记录包含：name, prompt, started_at, ended_at, returncode, status, stdout, stderr。
    """
    path = get_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_history(
    *,
    limit: int = 50,
    job_name: str | None = None,
    job_id: str | None = None,
) -> list[dict[str, Any]]:
    """加载最近的执行历史记录。

    Args:
        limit: 最大返回条数
        job_name: 按任务名称过滤
        job_id: 按任务 ID 过滤

    Returns:
        历史记录列表，按时间正序排列
    """
    path = get_history_path()
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if job_name and entry.get("name") != job_name:
            continue
        if job_id and entry.get("id") != job_id:
            continue
        entries.append(entry)
    return entries[-limit:]


# ---------------------------------------------------------------------------
# PID 文件管理
# ---------------------------------------------------------------------------

def get_pid_path() -> Path:
    """返回调度器 PID 文件路径。"""
    return get_data_dir() / "cron_scheduler.pid"


def read_pid() -> int | None:
    """读取运行中的调度器 PID，如果不存在或进程已退出则返回 None。"""
    path = get_pid_path()
    if not path.exists():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None
    # 检查进程是否存活
    try:
        os.kill(pid, 0)
    except OSError:
        logger.debug("Removed stale scheduler PID file (pid=%d)", pid)
        path.unlink(missing_ok=True)
        return None
    return pid


def write_pid(pid: int) -> None:
    """写入指定的进程 PID。"""
    path = get_pid_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid) + "\n", encoding="utf-8")


def remove_pid() -> None:
    """删除 PID 文件。"""
    get_pid_path().unlink(missing_ok=True)


def is_scheduler_running() -> bool:
    """返回是否存在运行的调度器进程。"""
    return read_pid() is not None


# ---------------------------------------------------------------------------
# 错误退避计算
# ---------------------------------------------------------------------------

def _get_backoff_seconds(consecutive_errors: int) -> int:
    """根据连续错误次数返回退避等待时间（秒）。

    使用预定义的退避序列，超出序列范围则使用最大值。
    """
    if consecutive_errors <= 0:
        return 0
    index = min(consecutive_errors - 1, len(_ERROR_BACKOFF_SECONDS) - 1)
    return _ERROR_BACKOFF_SECONDS[index]


# ---------------------------------------------------------------------------
# 可执行文件查找
# ---------------------------------------------------------------------------

def _find_illusion_command() -> list[str]:
    """查找 illusion 命令，返回可作为 subprocess 参数的命令列表。

    优先级：
    1. PATH 中的 illusion 可执行文件（pip install 后可用）
    2. python -m illusion（开发模式 / 模块运行）
    """
    # 方式 1：查找 PATH 中的 illusion 命令
    which = shutil.which("illusion")
    if which:
        return [which]

    # 方式 2：使用当前 Python 解释器运行模块
    return [sys.executable, "-m", "illusion"]


# ---------------------------------------------------------------------------
# 任务执行
# ---------------------------------------------------------------------------

async def _execute_prompt_in_subprocess(
    prompt: str,
    cwd: Path,
    timeout: int = _JOB_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """在独立子进程中执行提示词。

    通过 `illusion -p "<prompt>"` 启动独立会话，
    确保不阻塞当前会话，且任务在隔离环境中运行。

    Args:
        prompt: 要执行的提示词
        cwd: 工作目录
        timeout: 超时秒数

    Returns:
        包含 returncode, stdout, stderr, status 的结果字典
    """
    cmd = _find_illusion_command() + ["-p", prompt]

    logger.info("Executing cron subprocess: %s", " ".join(cmd[:3]) + " -p <prompt>")
    logger.debug("Full command: %s, cwd: %s", cmd, cwd)

    try:
        # Windows: 使用 CREATE_NO_WINDOW 防止弹出黑色控制台窗口
        # 非 Windows 平台该标志不存在，设为 0 不影响行为
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # Windows: 防止句柄继承死锁
            stdin=asyncio.subprocess.DEVNULL,
            # Windows: 不弹出控制台窗口
            creationflags=creationflags,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        # 超时处理：终止子进程
        try:
            process.kill()
            await process.wait()
        except Exception:
            pass
        logger.warning("Cron subprocess timed out after %ds", timeout)
        return {
            "returncode": -1,
            "status": "timeout",
            "stdout": "",
            "stderr": f"Job timed out after {timeout}s",
        }
    except FileNotFoundError as exc:
        # illusion 命令未找到
        logger.error("Failed to start cron subprocess: %s", exc)
        return {
            "returncode": -1,
            "status": "error",
            "stdout": "",
            "stderr": f"illusion command not found: {exc}",
        }
    except Exception as exc:
        logger.error("Failed to start cron subprocess: %s", exc)
        return {
            "returncode": -1,
            "status": "error",
            "stdout": "",
            "stderr": str(exc),
        }

    success = process.returncode == 0
    stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

    # 记录子进程 stderr 到日志（便于调试）
    if stderr_text.strip():
        logger.debug("Cron subprocess stderr: %s", stderr_text[:500])

    if not success:
        logger.warning(
            "Cron subprocess exited with rc=%d, stderr: %s",
            process.returncode,
            stderr_text[:200],
        )

    return {
        "returncode": process.returncode,
        "status": "success" if success else "failed",
        "stdout": (stdout.decode("utf-8", errors="replace")[-2000:] if stdout else ""),
        "stderr": stderr_text[-2000:] if stderr_text else "",
    }


async def execute_job(job: dict[str, Any]) -> dict[str, Any]:
    """执行单个 Cron 任务并返回历史记录条目。

    任务通过 `illusion -p` 在独立子进程中执行，不阻塞当前会话。

    Args:
        job: 任务字典，包含 name, prompt, cwd 等字段

    Returns:
        历史记录条目字典
    """
    name = job.get("name", job.get("id", "unknown"))
    prompt = job.get("prompt", "")
    cwd = Path(job.get("cwd") or ".").expanduser()
    started_at = _now_local()

    if not prompt:
        entry = {
            "id": job.get("id", ""),
            "name": name,
            "prompt": prompt,
            "started_at": started_at.isoformat(),
            "ended_at": _now_local().isoformat(),
            "returncode": -1,
            "status": "error",
            "stdout": "",
            "stderr": "Job has no prompt field",
        }
        logger.error("Cron job %r has no prompt, skipping", name)
        mark_job_run(job.get("id", name), success=False, status="error")
        append_history(entry)
        return entry

    logger.info("Executing cron job %r: %.80s", name, prompt)

    # 在独立子进程中执行提示词
    result = await _execute_prompt_in_subprocess(prompt, cwd)

    ended_at = _now_local()
    success = result["status"] == "success"

    entry = {
        "id": job.get("id", ""),
        "name": name,
        "prompt": prompt,
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "returncode": result["returncode"],
        "status": result["status"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }

    # 更新任务执行状态
    mark_job_run(job.get("id", name), success=success, status=result["status"])

    # 记录历史
    append_history(entry)
    logger.info(
        "Cron job %r finished: status=%s rc=%s",
        name,
        result["status"],
        result["returncode"],
    )

    return entry


def _now_local() -> datetime:
    """返回本地时间。"""
    return datetime.now().replace(microsecond=0)


# ---------------------------------------------------------------------------
# 调度器核心类
# ---------------------------------------------------------------------------

def _jobs_due(jobs: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """返回当前时间到期的任务列表。

    检查条件：
    1. 任务已启用
    2. cron 表达式有效
    3. next_run 时间已到
    4. 不在错误退避期内

    Args:
        jobs: 任务列表
        now: 当前本地时间

    Returns:
        到期任务列表
    """
    due: list[dict[str, Any]] = []
    for job in jobs:
        # 跳过禁用的任务
        if not job.get("enabled", True):
            continue

        # 验证 cron 表达式
        schedule = job.get("schedule", "")
        if not validate_cron_expression(schedule):
            continue

        # 检查 next_run
        next_run_str = job.get("next_run")
        if not next_run_str:
            continue
        try:
            next_run = datetime.fromisoformat(next_run_str)
            # 兼容旧格式：移除时区信息进行比较
            if next_run.tzinfo is not None:
                next_run = next_run.replace(tzinfo=None)
        except (ValueError, TypeError):
            continue

        # 检查是否到期
        if next_run > now:
            continue

        # 检查错误退避
        consecutive_errors = job.get("consecutive_errors", 0)
        if consecutive_errors > 0:
            last_run_str = job.get("last_run")
            if last_run_str:
                try:
                    last_run = datetime.fromisoformat(last_run_str)
                    if last_run.tzinfo is not None:
                        last_run = last_run.replace(tzinfo=None)
                    backoff = _get_backoff_seconds(consecutive_errors)
                    elapsed = (now - last_run).total_seconds()
                    if elapsed < backoff:
                        continue
                except (ValueError, TypeError):
                    pass

        due.append(job)

    return due


class CronScheduler:
    """Cron 调度器。

    作为后台 asyncio 任务运行，不阻塞当前会话。
    每个 tick 检查到期任务，在独立子进程中执行。

    使用方式：
        scheduler = get_scheduler()
        await scheduler.start()   # 启动
        await scheduler.stop()    # 停止
    """

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._shutdown = asyncio.Event()
        self._running = False

    @property
    def is_running(self) -> bool:
        """调度器是否正在运行。"""
        return self._running and self._task is not None and not self._task.done()

    async def start(self) -> None:
        """启动调度器后台任务。

        调度器作为 asyncio.Task 运行，不阻塞当前会话。
        如果已在运行则忽略。
        """
        if self.is_running:
            logger.debug("Scheduler already running, ignoring duplicate start")
            return

        self._shutdown.clear()
        self._running = True
        write_pid(os.getpid())

        # 创建后台任务
        self._task = asyncio.create_task(
            self._run_loop(),
            name="cron-scheduler",
        )
        logger.info("Cron scheduler started (tick=%ds)", TICK_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """停止调度器后台任务。"""
        if not self.is_running:
            return

        self._shutdown.set()
        self._running = False

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self._task = None
        remove_pid()
        logger.info("Cron scheduler stopped")

    async def _run_loop(self) -> None:
        """调度器主循环。"""
        write_pid(os.getpid())

        try:
            while not self._shutdown.is_set():
                await self._tick()

                # 清理已完成的一次性任务
                removed = remove_expired_jobs()
                if removed:
                    logger.info("Cleaned up %d expired cron job(s)", len(removed))

                # 等待下一个 tick 或关闭信号
                try:
                    await asyncio.wait_for(
                        self._shutdown.wait(),
                        timeout=TICK_INTERVAL_SECONDS,
                    )
                    break
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            logger.debug("Scheduler loop cancelled")
        except Exception:
            logger.exception("Scheduler loop crashed")
        finally:
            self._running = False
            remove_pid()

    async def _tick(self) -> None:
        """单次调度周期：检查到期任务并执行。"""
        now = _now_local()
        jobs = load_cron_jobs()
        due = _jobs_due(jobs, now)

        if not due:
            return

        logger.info("Tick: %d job(s) due", len(due))

        # 受并发限制执行任务
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_JOBS)

        async def _run_with_limit(job: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await execute_job(job)

        # 并发执行到期任务
        results = await asyncio.gather(
            *(_run_with_limit(job) for job in due),
            return_exceptions=True,
        )

        # 记录异常
        for result in results:
            if isinstance(result, BaseException):
                logger.error("Unexpected error executing cron job: %s", result)

    def status(self) -> dict[str, Any]:
        """返回调度器状态信息。"""
        jobs = load_cron_jobs()
        enabled = [j for j in jobs if j.get("enabled", True)]
        log_path = get_logs_dir() / "cron_scheduler.log"
        return {
            "running": self.is_running,
            "pid": os.getpid() if self.is_running else None,
            "total_jobs": len(jobs),
            "enabled_jobs": len(enabled),
            "log_file": str(log_path),
            "history_file": str(get_history_path()),
        }


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_scheduler: CronScheduler | None = None


def get_scheduler() -> CronScheduler:
    """获取全局调度器单例。"""
    global _scheduler
    if _scheduler is None:
        _scheduler = CronScheduler()
    return _scheduler


async def ensure_started() -> None:
    """确保调度器正在运行。如果未运行则自动启动。

    在创建 cron 任务时调用，确保调度器自动启动。
    """
    scheduler = get_scheduler()
    if not scheduler.is_running:
        await scheduler.start()


# ---------------------------------------------------------------------------
# 向后兼容的函数接口
# ---------------------------------------------------------------------------

def scheduler_status() -> dict[str, Any]:
    """返回调度器状态信息字典（向后兼容函数接口）。"""
    return get_scheduler().status()


def start_daemon() -> int:
    """启动调度器守护进程。

    注意：此函数为向后兼容保留。推荐使用 ensure_started()。

    Returns:
        当前进程 PID
    """
    write_pid(os.getpid())
    return os.getpid()


def stop_scheduler() -> bool:
    """停止调度器。

    注意：此函数为向后兼容保留。推荐使用 get_scheduler().stop()。

    Returns:
        是否成功停止
    """
    global _scheduler
    if _scheduler and _scheduler.is_running:
        _scheduler._shutdown.set()
        _scheduler._running = False
        remove_pid()
        return True
    pid = read_pid()
    if pid is None:
        return False
    remove_pid()
    return True


# 导出的公共接口
__all__ = [
    "CronScheduler",
    "get_scheduler",
    "ensure_started",
    "scheduler_status",
    "start_daemon",
    "stop_scheduler",
    "is_scheduler_running",
    "execute_job",
    "append_history",
    "load_history",
    "TICK_INTERVAL_SECONDS",
]
