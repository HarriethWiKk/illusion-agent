"""agent_executor 取消模型测试。"""

from __future__ import annotations

import asyncio

import pytest

from illusion.swarm.agent_executor import AgentAbortController, AgentExecutionContext  # noqa: F401
from illusion.utils.aioqueue import Queue


def test_cancel_event_triggers_shutdown():
    """cancel_event 触发后 message_queue 被 shutdown，consumer 退出。"""
    pytest.skip("需要 Task 10 完成后实现完整测试")


def test_timeout_triggers_force_cancel():
    """超时后 force_cancel 被设置。"""
    pytest.skip("需要 Task 10 完成后实现完整测试")


def test_message_queue_shutdown_wakes_consumer():
    """message_queue.shutdown() 唤醒 await get() 的 consumer。"""

    async def run():
        ctx = AgentExecutionContext(
            agent_id="test",
            agent_name="test",
            message_queue=Queue(),
        )
        messages = []
        consumer_task = asyncio.create_task(_message_consumer(messages, ctx))
        await asyncio.sleep(0.05)  # 让 consumer 进入 await get()
        ctx.message_queue.shutdown()
        await consumer_task  # 应立即完成
        assert messages == []

    from illusion.swarm.agent_executor import _message_consumer

    asyncio.run(run())
