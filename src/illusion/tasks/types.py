"""
任务数据模型模块
================

本模块定义任务相关的数据类型。

类型说明：
    - TaskType: 任务类型
    - TaskStatus: 任务状态
    - TaskUpdateStatus: 任务更新状态（含 deleted）

类说明：
    - TaskRecord: 后台任务的运行时表示
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

# 任务类型
TaskType = Literal["local_bash", "local_agent", "remote_agent", "in_process_teammate", "in_process_agent"]
# 任务状态
TaskStatus = Literal["pending", "running", "completed", "failed", "killed"]
# 对外显示状态
TaskDisplayStatus = Literal["pending", "in_progress", "completed", "failed", "killed"]

# 扩展状态，包含任务更新操作的 deleted
TaskUpdateStatus = Literal["pending", "in_progress", "completed", "deleted"]

_INTERNAL_TO_DISPLAY_STATUS: dict[str, str] = {
    "pending": "pending",
    "running": "in_progress",
    "completed": "completed",
    "failed": "failed",
    "killed": "killed",
}

_DISPLAY_TO_INTERNAL_STATUS: dict[str, str] = {
    "pending": "pending",
    "in_progress": "running",
    "completed": "completed",
    "failed": "failed",
    "killed": "killed",
}


def to_task_display_status(status: TaskStatus | str) -> TaskDisplayStatus | str:
    """将内部任务状态转换为对外显示状态。"""
    mapped = _INTERNAL_TO_DISPLAY_STATUS.get(status)
    if mapped is None:
        return status
    return cast(TaskDisplayStatus, mapped)


def to_task_internal_status(status: TaskUpdateStatus | TaskDisplayStatus | TaskStatus | str) -> TaskStatus:
    """将对外状态转换为内部任务状态。"""
    mapped = _DISPLAY_TO_INTERNAL_STATUS.get(status, status)
    if mapped not in {"pending", "running", "completed", "failed", "killed"}:
        raise ValueError(f"Unsupported task status: {status}")
    return cast(TaskStatus, mapped)


@dataclass
class TaskRecord:
    """后台任务的运行时表示。

    支持两类后台任务：
    - 子进程任务（local_bash / local_agent / remote_agent）：通过 _processes 管理
    - 进程内异步任务（in_process_agent）：通过 async_task 字段持有的 asyncio.Task 引用管理
      该类型用于 agent_tool 的进程内后台模式，可被 task_stop 取消，输出累积到 output_file
    """

    id: str
    type: TaskType
    status: TaskStatus
    description: str
    cwd: str
    output_file: Path
    command: str | None = None
    prompt: str | None = None
    subject: str | None = None
    active_form: str | None = None
    owner: str | None = None
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    created_at: float = 0.0
    started_at: float | None = None
    ended_at: float | None = None
    return_code: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    comments: list[str] = field(default_factory=list)
    # 进程内异步任务引用（仅 in_process_agent 类型使用）
    # 持有 asyncio.Task 引用使 task_stop 可以通过 task.cancel() 终止后台 agent
    async_task: Any | None = None
    # 进程内 agent 的最终结果文本（任务完成后填充，供 task_output 读取）
    result: str | None = None
    # agent 完成时的最终文本回复摘要（供 /agent 命令查看）
    summary: str | None = None
