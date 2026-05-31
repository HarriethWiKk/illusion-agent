"""
统一 Cron 定时任务工具
======================

对齐 openclaw 的 cron 工具设计，将创建、列表、删除、开关、手动触发
合并为单一工具，通过 action 参数区分操作。

支持的操作（actions）：
    - status: 查看调度器状态
    - list: 列出所有定时任务
    - add: 创建新的定时任务
    - update: 修改已有任务（启用/禁用、更新计划等）
    - remove: 删除定时任务
    - run: 手动触发执行任务

数据模型（对齐 openclaw CronJob）：
    - id: 唯一标识符（自动生成）
    - name: 人类可读名称
    - schedule: 5 字段 cron 表达式（本地时间）
    - prompt: 触发时执行的提示词
    - enabled: 是否启用
    - recurring: 是否重复执行
    - delete_after_run: 执行后自动删除

使用示例：
    >>> from illusion.tools.cron_tool import CronTool
    >>> tool = CronTool()
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from illusion.services.cron import (
    delete_cron_job,
    get_cron_job,
    load_cron_jobs,
    set_job_enabled,
    upsert_cron_job,
    validate_cron_expression,
)
from illusion.services.cron_scheduler import (
    execute_job,
    get_scheduler,
    is_scheduler_running,
)
from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult

# 支持的操作列表
_ACTIONS = ("status", "list", "add", "update", "remove", "run")


class CronToolInput(BaseModel):
    """统一 Cron 工具参数。

    属性：
        action: 操作类型
        name: 任务名称（add 可选；update/remove/run 必填）
        schedule: 5 字段 cron 表达式（add/update）
        prompt: 触发时执行的提示词（add 必填；update 可选）
        recurring: 是否重复执行（add/update）
        delete_after_run: 执行后自动删除（add/update）
        enabled: 启用/禁用状态（update）
        include_disabled: 列表是否包含禁用任务（list）
        timeout_seconds: 手动运行超时秒数（run）
    """

    action: str = Field(
        description=f"Action: {', '.join(_ACTIONS)}",
    )
    # add/update 操作通用参数
    name: str | None = Field(
        default=None,
        description="Job name or ID (optional for add; required for update/remove/run)",
    )
    schedule: str | None = Field(
        default=None,
        description="5-field cron expression in local time (add/update). E.g. '*/5 * * * *', '0 9 * * 1-5'",
    )
    prompt: str | None = Field(
        default=None,
        description="Prompt to execute in an isolated session when the job fires (required for add; optional for update)",
    )
    recurring: bool | None = Field(
        default=None,
        description="True = fire on every cron match until deleted. False = fire once then auto-delete. Set to true/false to change (add/update).",
    )
    delete_after_run: bool | None = Field(
        default=None,
        description="Delete the job record after execution (add/update). Set to true/false to change.",
    )
    # update 操作参数
    enabled: bool | None = Field(
        default=None,
        description="Enable or disable the job (update)",
    )
    # list 操作参数
    include_disabled: bool = Field(
        default=False,
        description="Include disabled jobs in list output",
    )
    # run 操作参数
    timeout_seconds: int = Field(
        default=300,
        ge=1,
        le=3600,
        description="Timeout in seconds for manual run",
    )


class CronTool(BaseTool):
    """Manage scheduled cron jobs (status/list/add/update/remove/run).

    Aligned with openclaw's cron tool design.
    Jobs execute in isolated sessions via `illusion -p`, not blocking the current session.
    Uses standard 5-field cron expressions in the user's local timezone.
    """

    name = "cron"
    description = """Manage scheduled cron jobs (status/list/add/update/remove/run). Use for reminders, delayed follow-ups, and recurring tasks. Do not emulate scheduling with exec sleep.

ACTIONS:
- status: Check scheduler status and job counts
- list: List all scheduled jobs (use include_disabled:true to show disabled)
- add: Create a new scheduled job (requires schedule, prompt; optional name)
- update: Modify an existing job (requires name; can update schedule/prompt/recurring/delete_after_run/enabled)
- remove: Delete a job (requires name)
- run: Manually trigger a job immediately (requires name)

SCHEDULE (standard 5-field cron, user's local time):
- minute hour day-of-month month day-of-week
- "*/5 * * * *" = every 5 minutes
- "0 * * * *" = every hour
- "0 9 * * 1-5" = weekdays at 9am local
- "30 14 7 5 *" = May 7th at 2:30pm

ONE-SHOT EXAMPLES:
  "remind me at 2:30pm today" -> schedule: "30 14 <today_dom> <today_month> *", recurring: false
  "run smoke test tomorrow morning" -> schedule: "57 8 <tomorrow_dom> <tomorrow_month> *", recurring: false

AVOID :00 AND :30 when the task allows it:
  "every morning around 9" -> "57 8 * * *" or "3 9 * * *" (not "0 9 * * *")
  "hourly" -> "7 * * * *" (not "0 * * * *")

EXECUTION:
  Jobs run via `illusion -p` in an isolated subprocess, not blocking the current session.
  The scheduler auto-starts when a job is created.
  Recurring jobs do not auto-expire; delete them manually when no longer needed.

Returns JSON result for each action."""
    input_model = CronToolInput

    async def execute(
        self,
        arguments: CronToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        action = arguments.action.strip().lower()

        if action not in _ACTIONS:
            return ToolResult(
                output=f"Unknown action: {action!r}. Supported: {', '.join(_ACTIONS)}",
                is_error=True,
            )

        handler = {
            "status": self._handle_status,
            "list": self._handle_list,
            "add": self._handle_add,
            "update": self._handle_update,
            "remove": self._handle_remove,
            "run": self._handle_run,
        }[action]

        return await handler(arguments, context)

    # ------------------------------------------------------------------
    # status: 调度器状态
    # ------------------------------------------------------------------

    async def _handle_status(
        self,
        arguments: CronToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        """查看调度器运行状态和任务统计。"""
        del arguments, context

        scheduler = get_scheduler()
        status = scheduler.status()

        state = "running" if status["running"] else "stopped"
        lines = [
            f"Scheduler: {state}",
            f"Total jobs: {status['total_jobs']}",
            f"Enabled: {status['enabled_jobs']}",
        ]
        if status.get("pid"):
            lines.append(f"PID: {status['pid']}")

        return ToolResult(output="\n".join(lines))

    # ------------------------------------------------------------------
    # list: 列出任务
    # ------------------------------------------------------------------

    async def _handle_list(
        self,
        arguments: CronToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        """列出所有定时任务。"""
        del context

        jobs = load_cron_jobs()

        if not arguments.include_disabled:
            jobs = [j for j in jobs if j.get("enabled", True)]

        if not jobs:
            return ToolResult(output="No cron jobs configured.")

        scheduler_state = "running" if is_scheduler_running() else "stopped"
        lines = [f"Scheduler: {scheduler_state}", ""]

        for job in jobs:
            enabled = "+" if job.get("enabled", True) else "-"
            name = job.get("name", job.get("id", "?"))
            schedule = job.get("schedule", "?")
            recurring = "recurring" if job.get("recurring", True) else "one-shot"

            last_run = job.get("last_run", "never")
            if last_run != "never":
                last_run = last_run[:19]
            last_status = job.get("last_status", "")
            status_str = f" ({last_status})" if last_status else ""

            next_run = job.get("next_run", "n/a")
            if next_run != "n/a":
                next_run = next_run[:19]

            errors = job.get("consecutive_errors", 0)
            error_str = f" [errors: {errors}]" if errors > 0 else ""

            lines.append(
                f"[{enabled}] {name}  {schedule} ({recurring})\n"
                f"     prompt: {job.get('prompt', '?')[:60]}\n"
                f"     last: {last_run}{status_str}  next: {next_run}{error_str}"
            )

        return ToolResult(output="\n".join(lines))

    # ------------------------------------------------------------------
    # add: 创建任务
    # ------------------------------------------------------------------

    async def _handle_add(
        self,
        arguments: CronToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        """创建新的定时任务，并自动启动调度器。"""
        if not arguments.schedule:
            return ToolResult(
                output="Missing required parameter: schedule\n"
                "Use a 5-field cron expression, e.g. '*/5 * * * *' (every 5 min)",
                is_error=True,
            )

        if not arguments.prompt:
            return ToolResult(
                output="Missing required parameter: prompt\n"
                "prompt is executed in an isolated session when the job fires",
                is_error=True,
            )

        if not validate_cron_expression(arguments.schedule):
            return ToolResult(
                output=(
                    f"Invalid cron expression: {arguments.schedule!r}\n"
                    "Use 5-field format: minute hour day month weekday\n"
                    "Examples: '*/5 * * * *' (every 5 min), '0 9 * * 1-5' (weekdays 9am)"
                ),
                is_error=True,
            )

        # 构建任务字典
        job_data: dict[str, Any] = {
            "schedule": arguments.schedule.strip(),
            "prompt": arguments.prompt,
            "recurring": arguments.recurring
            if arguments.recurring is not None
            else True,
            "delete_after_run": arguments.delete_after_run
            if arguments.delete_after_run is not None
            else False,
            "cwd": str(context.cwd),
        }

        if arguments.name:
            job_data["name"] = arguments.name.strip()

        # 创建任务
        job_id = upsert_cron_job(job_data)

        # 自动启动调度器（如果未运行）
        try:
            scheduler = get_scheduler()
            if not scheduler.is_running:
                await scheduler.start()
        except Exception:
            # 调度器启动失败不应阻止任务创建
            pass

        kind = "recurring" if (arguments.recurring if arguments.recurring is not None else True) else "one-shot"
        name_display = arguments.name or job_id
        return ToolResult(
            output=f"Created {kind} job '{name_display}' [{arguments.schedule}] (id: {job_id})"
        )

    # ------------------------------------------------------------------
    # update: 修改任务
    # ------------------------------------------------------------------

    async def _handle_update(
        self,
        arguments: CronToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        """修改已有任务的计划、启用状态等。"""
        del context

        if not arguments.name:
            return ToolResult(
                output="Missing required parameter: name (job name or ID to update)",
                is_error=True,
            )

        job = get_cron_job(arguments.name)
        if job is None:
            return ToolResult(
                output=f"Cron job not found: {arguments.name}",
                is_error=True,
            )

        changes: list[str] = []

        if arguments.enabled is not None:
            if set_job_enabled(arguments.name, arguments.enabled):
                state = "enabled" if arguments.enabled else "disabled"
                changes.append(f"{state}")
            else:
                return ToolResult(
                    output=f"Failed to update job: {arguments.name}",
                    is_error=True,
                )

        if arguments.schedule is not None:
            if not validate_cron_expression(arguments.schedule):
                return ToolResult(
                    output=f"Invalid cron expression: {arguments.schedule!r}",
                    is_error=True,
                )
            job["schedule"] = arguments.schedule.strip()
            upsert_cron_job(job)
            changes.append(f"schedule={arguments.schedule.strip()}")

        if arguments.prompt is not None:
            job["prompt"] = arguments.prompt
            upsert_cron_job(job)
            changes.append("prompt updated")

        if arguments.recurring is not None:
            if arguments.recurring != job.get("recurring", True):
                job["recurring"] = arguments.recurring
                upsert_cron_job(job)
                changes.append(f"recurring={arguments.recurring}")

        if arguments.delete_after_run is not None:
            if arguments.delete_after_run != job.get("delete_after_run", False):
                job["delete_after_run"] = arguments.delete_after_run
                upsert_cron_job(job)
                changes.append(f"delete_after_run={arguments.delete_after_run}")

        if changes:
            return ToolResult(
                output=f"Updated cron job: {arguments.name} ({', '.join(changes)})"
            )
        else:
            return ToolResult(
                output="No fields to update (available: schedule, prompt, recurring, enabled, delete_after_run)",
                is_error=True,
            )

    # ------------------------------------------------------------------
    # remove: 删除任务
    # ------------------------------------------------------------------

    async def _handle_remove(
        self,
        arguments: CronToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        """删除定时任务。"""
        del context

        if not arguments.name:
            return ToolResult(
                output="Missing required parameter: name (job name or ID to remove)",
                is_error=True,
            )

        if not delete_cron_job(arguments.name):
            return ToolResult(
                output=f"Cron job not found: {arguments.name}",
                is_error=True,
            )

        return ToolResult(output=f"Deleted cron job: {arguments.name}")

    # ------------------------------------------------------------------
    # run: 手动触发
    # ------------------------------------------------------------------

    async def _handle_run(
        self,
        arguments: CronToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        """手动触发执行定时任务。"""
        del context

        if not arguments.name:
            return ToolResult(
                output="Missing required parameter: name (job name or ID to run)",
                is_error=True,
            )

        job = get_cron_job(arguments.name)
        if job is None:
            return ToolResult(
                output=f"Cron job not found: {arguments.name}",
                is_error=True,
            )

        prompt = job.get("prompt", "")
        if not prompt:
            return ToolResult(
                output=f"Job has no prompt: {arguments.name}",
                is_error=True,
            )

        # 在独立会话中执行
        entry = await execute_job(job, timeout=arguments.timeout_seconds)

        status = entry.get("status", "unknown")
        returncode = entry.get("returncode", "?")
        stdout = entry.get("stdout", "").strip()
        stderr = entry.get("stderr", "").strip()

        parts = [f"Triggered {arguments.name} ({status}, rc={returncode})"]
        if stdout:
            parts.append(f"Output:\n{stdout}")
        if stderr and status != "success":
            parts.append(f"Error:\n{stderr}")

        return ToolResult(
            output="\n".join(parts),
            is_error=status != "success",
            metadata={"returncode": returncode, "status": status},
        )
