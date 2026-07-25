"""BackgroundAgentTracker shutdown + 超时保护测试。"""

from __future__ import annotations

import asyncio

from illusion.engine.query import BackgroundAgentTracker


def test_shutdown_wakes_waiters():
    """shutdown 唤醒所有 wait_for_completion 等待者。"""

    async def run():
        tracker = BackgroundAgentTracker()
        tracker.register("agent_1")
        # 启动一个 wait_for_completion task
        wait_task = asyncio.create_task(tracker.wait_for_completion())
        await asyncio.sleep(0.05)  # 让 wait_task 进入等待
        # shutdown 应唤醒等待者
        tracker.shutdown()
        result = await asyncio.wait_for(wait_task, timeout=1.0)
        # shutdown 后返回当前已收集的 completions（应为空）
        assert result == []

    asyncio.run(run())


def test_wait_for_completion_timeout():
    """wait_for_completion 超时后返回当前 completions。"""

    async def run():
        tracker = BackgroundAgentTracker()
        tracker.register("agent_1")
        # 超时后应返回空列表（无 completion）
        result = await tracker.wait_for_completion(timeout=0.1)
        assert result == []
        # tracker 仍可继续使用
        assert tracker.has_pending()

    asyncio.run(run())


def test_notify_completed_guard_against_negative():
    """重复 notify 不会使 _pending_count 变负。"""

    tracker = BackgroundAgentTracker()
    tracker.register("agent_1")
    # 第一次 notify 正常
    tracker.notify_completed("agent_1", "<notification>1</notification>")
    assert tracker._pending_count == 0
    # 重复 notify 不应使 _pending_count 变负
    tracker.notify_completed("agent_1", "<notification>2</notification>")
    assert tracker._pending_count == 0  # guard 生效
    # completions 仍累积（避免丢失通知）
    assert len(tracker._completions) == 2


def test_shutdown_is_idempotent():
    """shutdown 多次调用安全。"""

    tracker = BackgroundAgentTracker()
    tracker.register("agent_1")
    tracker.shutdown()
    tracker.shutdown()  # 不应抛异常
    assert tracker._shutdown is True


def test_notify_after_shutdown_is_noop():
    """shutdown 后 notify_completed 是 no-op。"""

    tracker = BackgroundAgentTracker()
    tracker.shutdown()
    tracker.notify_completed("agent_1", "<notification>1</notification>")
    # shutdown 后不应累积 completion
    assert len(tracker._completions) == 0


def test_wait_for_completion_after_shutdown_returns_immediately():
    """shutdown 后 wait_for_completion 立即返回。"""

    async def run():
        tracker = BackgroundAgentTracker()
        tracker.shutdown()
        result = await tracker.wait_for_completion(timeout=1.0)
        assert result == []

    asyncio.run(run())
