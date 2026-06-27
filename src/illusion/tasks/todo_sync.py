"""
Todo 与 Task 双向同步模块
========================

本模块提供 todo 列表与后台 task 的双向同步功能，使二者完全等效互通。

设计要点：
    - 只有 type="in_process_teammate" 的 task 参与 todo 互通；
      其他类型（local_bash/local_agent/remote_agent）是子进程任务，不属于 todo 范畴。
    - Todo 无 ID，Task 有 ID。基于 content 文本派生稳定 ID（sha1 前 8 位），
      保证同一 todo 多次写入映射到同一 task，避免重复创建。
    - 状态双向映射：pending↔pending、in_progress↔running、completed↔completed；
      failed/killed 在 todo 视图分别回退为 in_progress/pending（todo 无失败态）。

主要函数：
    - todos_from_tasks: 从 task 列表提取 todo dict 列表（Task → Todo）
    - sync_todos_to_tasks: 将 todo 列表全量同步到 manager（Todo → Task）

使用示例：
    >>> from illusion.tasks.manager import get_task_manager
    >>> from illusion.tasks.todo_sync import sync_todos_to_tasks, todos_from_tasks
    >>> manager = get_task_manager()
    >>> # Todo 写入时同步到 task
    >>> sync_todos_to_tasks([{"content": "运行测试", "status": "in_progress", "activeForm": "正在运行测试"}], manager)
    >>> # Task 变更时同步到 todo
    >>> todos = todos_from_tasks(manager.list_tasks())
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from illusion.config.paths import get_tasks_dir
from illusion.tasks.manager import BackgroundTaskManager
from illusion.tasks.types import TaskRecord, to_task_display_status


# 参与 todo 互通的 task 类型
TODO_TASK_TYPE = "in_process_teammate"

# Todo 状态 → Task 内部状态
_TODO_TO_TASK_STATUS: dict[str, str] = {
    "pending": "pending",
    "in_progress": "running",
    "completed": "completed",
}

# Task 显示状态 → Todo 状态（failed/killed 回退到 todo 可表达的状态）
_TASK_TO_TODO_STATUS: dict[str, str] = {
    "pending": "pending",
    "in_progress": "in_progress",
    "completed": "completed",
    "failed": "in_progress",
    "killed": "pending",
}


def _stable_task_id(content: str) -> str:
    """基于 content 文本派生稳定的 task ID。

    使用 sha1 前 8 位作为后缀，前缀 `t` 与 manager 中 in_process_teammate 类型一致。
    """
    digest = hashlib.sha1(content.encode("utf-8")).hexdigest()[:8]
    return f"t{digest}"


def todos_from_tasks(tasks: list[TaskRecord]) -> list[dict[str, Any]]:
    """从 task 列表提取 todo dict 列表（仅 in_process_teammate 类型）。

    字段映射与 TaskSnapshot.from_record 保持一致：显示名统一取 task.description，
    确保 task 渲染（TaskSnapshot.description）与 todo 渲染（content）显示同一个名字。

    Args:
        tasks: task 记录列表

    Returns:
        todo dict 列表，每项包含 content/status/activeForm
    """
    todos: list[dict[str, Any]] = []
    for task in tasks:
        if task.type != TODO_TASK_TYPE:
            continue
        # TaskRecord.status 是内部状态（如 running），先转显示状态再映射到 todo 状态
        display_status = to_task_display_status(task.status)
        todo_status = _TASK_TO_TODO_STATUS.get(display_status)
        if todo_status is None:
            continue
        # 与 TaskSnapshot.from_record 一致，优先用 description 作为对外显示名；
        # 仅当 description 为空时回退到 subject，保证内容不丢失
        content = (task.description or task.subject or "").strip()
        if not content:
            continue
        active_form = (task.active_form or "").strip() or content
        todos.append({
            "content": content,
            "status": todo_status,
            "activeForm": active_form,
        })
    return todos


def sync_todos_to_tasks(
    todos: list[dict[str, Any]],
    manager: BackgroundTaskManager,
) -> list[TaskRecord]:
    """将 todo 列表全量同步到 manager 的 in_process_teammate 任务。

    - 对每个 todo：基于 content 派生稳定 ID，创建或更新对应 task
    - 对 manager 中不在新 todo 列表的 in_process_teammate 任务，删除
    - 保留其他类型（local_bash/local_agent/remote_agent）的 task 不变

    Args:
        todos: todo dict 列表
        manager: 后台任务管理器

    Returns:
        同步后的完整 task 列表（含非 in_process_teammate 类型）
    """
    new_task_ids: set[str] = set()

    for todo in todos:
        content = (todo.get("content") or "").strip()
        if not content:
            continue

        task_id = _stable_task_id(content)
        new_task_ids.add(task_id)

        todo_status = todo.get("status", "pending")
        task_status = _TODO_TO_TASK_STATUS.get(todo_status, "pending")
        active_form = todo.get("activeForm") or content

        existing = manager.get_task(task_id)
        if existing is None:
            # 创建新 task（直接操作内部字典以使用派生的稳定 ID）
            output_path = get_tasks_dir() / f"{task_id}.log"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("", encoding="utf-8")
            record = TaskRecord(
                id=task_id,
                type=TODO_TASK_TYPE,
                status=task_status,  # type: ignore[arg-type]
                description=content,
                subject=content,
                active_form=active_form,
                cwd=str(Path.cwd().resolve()),
                output_file=output_path,
                created_at=time.time(),
            )
            manager._tasks[task_id] = record
        else:
            # 更新现有 task 的可变字段
            existing.status = task_status  # type: ignore[assignment]
            existing.active_form = active_form
            existing.subject = content
            existing.description = content

    # 删除不在新 todo 列表中的 in_process_teammate 任务
    to_remove = [
        tid for tid, t in manager._tasks.items()
        if t.type == TODO_TASK_TYPE and tid not in new_task_ids
    ]
    for tid in to_remove:
        manager._tasks.pop(tid, None)

    return manager.list_tasks()


__all__ = ["todos_from_tasks", "sync_todos_to_tasks", "TODO_TASK_TYPE"]
