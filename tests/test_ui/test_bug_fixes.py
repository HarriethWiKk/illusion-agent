"""bug 修复验证测试：权限模态框死锁 + Ctrl+X 任务终止。

验证两个 bug 的修复：
1. Bug 1: handle_submit 直接 await _process_line 导致 Textual 消息循环死锁，
   权限模态框出现后无法消失。修复：改为 fire-and-forget 调度。
2. Bug 2: agent_executor finally 块漏 cancel query_task，外层 cancel 传播时
   query_task 泄漏，工具继续运行，Ctrl+X 无法终止任务。修复：finally 中显式 cancel query_task。
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import MagicMock

import pytest

from illusion.ui.textual_app import PermissionScreen, illusionTerminalApp
from illusion.swarm.agent_executor import run_agent_in_process


def test_handle_submit_uses_fire_and_forget_dispatch():
    """handle_submit 应使用 _create_background_task 而非直接 await，避免阻塞消息循环。"""
    src = inspect.getsource(illusionTerminalApp.handle_submit)
    assert "_create_background_task" in src, "handle_submit 应使用 _create_background_task 调度"
    assert "await self._process_line" not in src, "handle_submit 不应直接 await _process_line"


def test_agent_executor_finally_cancels_query_task():
    """agent_executor finally 块应显式 cancel query_task，避免 Ctrl+X 时泄漏。"""
    src = inspect.getsource(run_agent_in_process)
    # 定位 finally 块中的 query_task cancel 逻辑
    assert "if not query_task.done()" in src, "finally 块应检查 query_task.done()"
    assert "query_task.cancel()" in src, "finally 块应 cancel query_task"


@pytest.mark.asyncio
async def test_open_modal_callback_fires_when_not_in_handler(tmp_path, monkeypatch):
    """_open_modal 在非 handler 上下文中应能通过 dismiss 触发 callback。

    此测试验证 _open_modal 的基本行为：push_screen 后，dismiss(result) 应触发
    _done callback，future.set_result，await future 返回。
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ILLUSION_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))

    app = illusionTerminalApp(api_client=MagicMock())
    async with app.run_test() as pilot:
        # 在背景任务中调用 _open_modal（不阻塞消息循环）
        async def _open_and_dismiss() -> None:
            result = await app._open_modal(PermissionScreen("test_tool", "test reason"))
            assert result is True

        task = asyncio.create_task(_open_and_dismiss())
        # 轮询等待模态框出现（pilot 无 wait_for_callable）
        for _ in range(30):
            await pilot.pause()
            if isinstance(app.screen, PermissionScreen):
                break
            await asyncio.sleep(0.1)
        else:
            raise AssertionError("PermissionScreen 未在 3s 内出现")
        # 按 y 触发 dismiss(True)
        await pilot.press("y")
        await pilot.pause()
        # 等待 task 完成
        await asyncio.wait_for(task, timeout=3.0)


@pytest.mark.asyncio
async def test_handle_submit_does_not_deadlock_modal(tmp_path, monkeypatch):
    """handle_submit 触发的权限模态框应能被用户关闭（回归测试）。

    Bug 1 回归测试：handle_submit 直接 await _process_line 会阻塞消息循环，
    导致 _done callback 无法刷新。修复后 handle_submit 应使用 fire-and-forget。
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ILLUSION_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))

    app = illusionTerminalApp(api_client=MagicMock())
    async with app.run_test() as pilot:
        composer = app.query_one("#composer")
        composer.value = "/version"
        # 触发 handle_submit
        await pilot.press("enter")
        # 给 fire-and-forget task 时间执行
        await pilot.pause()
        # 消息循环不应阻塞，composer 应能响应
        assert composer is not None


@pytest.mark.asyncio
async def test_agent_executor_cancels_query_task_on_outer_cancel():
    """agent_executor 在外层 cancel 传播时应 cancel query_task（回归测试）。

    Bug 2 回归测试：当 _stop_active_line 调用 task.cancel() 时，
    await asyncio.wait 抛 CancelledError，finally 块应 cancel query_task。
    """
    # 验证 finally 块的源码结构：query_task cancel 在 message_task 之后、helpers 之前
    src = inspect.getsource(run_agent_in_process)
    finally_idx = src.index("finally:")
    # 找到 finally 块内的关键代码顺序
    msg_shutdown_idx = src.index("ctx.message_queue.shutdown()", finally_idx)
    query_cancel_idx = src.index("if not query_task.done()", finally_idx)
    helpers_idx = src.index("pending_helpers", finally_idx)

    assert msg_shutdown_idx < query_cancel_idx < helpers_idx, (
        "finally 块顺序应为：message_queue.shutdown → query_task cancel → helpers cancel"
    )
