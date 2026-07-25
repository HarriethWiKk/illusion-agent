"""ReactBackendHost 写路径重构测试。"""

from __future__ import annotations

import asyncio  # noqa: F401  Task 6 将启用
import pytest

from illusion.ui.backend_host import ReactBackendHost  # noqa: F401  Task 6 将启用
from illusion.utils.aioqueue import Queue, QueueShutDown  # noqa: F401  Task 6 将启用


def test_emit_puts_to_write_queue():
    """_emit 入队事件，不直接写 stdout。"""
    # 此测试需要构造 ReactBackendHost 实例
    # 由于是 breaking refactor，构造签名可能变化
    # 测试核心：_emit 调用后 _write_queue 非空
    pytest.skip("需要 Task 6 完成后集成测试")


def test_write_loop_consumes_queue():
    """_write_loop 串行消费 _write_queue。"""
    pytest.skip("需要 Task 6 完成后集成测试")


def test_create_background_task_keeps_strong_ref():
    """_create_background_task 保留强引用。"""
    pytest.skip("需要 Task 6 完成后集成测试")
