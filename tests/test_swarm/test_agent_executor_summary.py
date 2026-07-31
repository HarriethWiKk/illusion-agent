"""agent_executor 摘要捕获测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from illusion.tasks.types import TaskRecord


def test_task_record_has_summary_field():
    """TaskRecord 新增 summary 字段，默认 None。"""
    rec = TaskRecord(
        id="t1",
        type="in_process_agent",
        status="running",
        description="d",
        cwd=".",
        output_file=Path("/tmp/o.log"),
    )
    assert rec.summary is None
    rec.summary = "final answer"
    assert rec.summary == "final answer"


async def test_capture_agent_summary_writes_to_record_and_file(tmp_path):
    """capture_agent_summary 写入 TaskRecord.summary 并落盘 <agent-summary> 标签。"""
    from illusion.swarm import agent_executor

    output_file = tmp_path / "out.log"
    output_file.write_text("existing log\n", encoding="utf-8")

    record = TaskRecord(
        id="t1",
        type="in_process_agent",
        status="running",
        description="d",
        cwd=".",
        output_file=output_file,
    )

    manager = MagicMock()
    manager._tasks = {"t1": record}
    manager.update_task = MagicMock()

    with patch.object(agent_executor, "get_task_manager", return_value=manager):
        await agent_executor.capture_agent_summary(record.id, "the final reply", manager)

    assert record.summary == "the final reply"
    content = output_file.read_text(encoding="utf-8")
    assert "<agent-summary>the final reply</agent-summary>" in content
    # 验证 update_task 被调用并传入 summary 参数
    manager.update_task.assert_called_once_with(record.id, summary="the final reply")


async def test_capture_agent_summary_missing_task_is_noop(tmp_path):
    """task_id 不存在于 manager._tasks 时静默返回，不抛异常。"""
    from illusion.swarm import agent_executor

    output_file = tmp_path / "out.log"
    output_file.write_text("existing log\n", encoding="utf-8")

    manager = MagicMock()
    manager._tasks = {}
    manager.update_task = MagicMock()

    await agent_executor.capture_agent_summary("nonexistent", "text", manager)

    # 文件未被修改
    assert output_file.read_text(encoding="utf-8") == "existing log\n"
    manager.update_task.assert_not_called()
