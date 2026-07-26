"""调查：TUI 权限模态框不消失 bug 的行为测试。

复现用户报告的"权限模态框一直显示占用ui空间而没有正常消失"。

测试目标：
    1. 验证 _open_modal 在背景任务中调用时（初始 prompt 流程）模态框能正常消失
    2. 验证 _open_modal 在 handle_submit 同步上下文中调用时（用户输入流程）是否死锁
    3. 验证 PermissionScreen.dismiss 真正从屏幕栈中弹出
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from illusion.ui.textual_app import PermissionScreen, illusionTerminalApp


@pytest.mark.asyncio
async def test_modal_dismissed_when_opened_from_background_task(tmp_path, monkeypatch):
    """场景1：从背景任务调用 _open_modal（模拟初始 prompt 流程）。

    初始 prompt 流程：
        on_mount -> call_later -> _create_background_task -> _process_line
        -> handle_line -> ... -> _ask_permission -> _open_modal

    App 的消息循环不会被阻塞，应该能正常处理 _done 回调和 do_pop。
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ILLUSION_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))

    app = illusionTerminalApp(api_client=MagicMock())

    modal_result: asyncio.Future = asyncio.get_running_loop().create_future()

    async def _push_and_wait():
        """背景任务：调用 _open_modal 并等待结果。"""
        result = await app._open_modal(PermissionScreen("bash", "test reason"))
        if not modal_result.done():
            modal_result.set_result(result)

    async with app.run_test() as pilot:
        # App 启动后，从背景任务调用 _open_modal
        app._create_background_task(_push_and_wait())
        await pilot.pause()

        # 模态框应该已显示
        assert len(app.screen_stack) >= 2, f"模态框应已 push 到栈上，实际栈深度: {len(app.screen_stack)}"
        assert isinstance(app.screen, PermissionScreen), (
            f"栈顶应为 PermissionScreen，实际: {type(app.screen).__name__}"
        )

        # 模拟用户按 y 键（Allow）
        await pilot.press("y")
        await pilot.pause()
        # 再多等一下，让 _done 回调和 do_pop 完成
        await pilot.pause()

        # 验证模态框已消失
        assert modal_result.done(), (
            "背景任务的 _open_modal future 应已完成（_done 回调已执行）"
        )
        assert modal_result.result() is True, (
            f"模态框结果应为 True（Allow），实际: {modal_result.result()}"
        )
        # 栈顶不应再是 PermissionScreen
        assert not isinstance(app.screen, PermissionScreen), (
            f"栈顶不应再是 PermissionScreen，实际: {type(app.screen).__name__}；"
            f"栈深度: {len(app.screen_stack)}"
        )


@pytest.mark.asyncio
async def test_modal_dismissed_via_button_click(tmp_path, monkeypatch):
    """场景2：通过 Tab 聚焦 Allow 按钮后回车关闭模态框。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ILLUSION_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))

    app = illusionTerminalApp(api_client=MagicMock())

    modal_result: asyncio.Future = asyncio.get_running_loop().create_future()

    async def _push_and_wait():
        result = await app._open_modal(PermissionScreen("bash", "test reason"))
        if not modal_result.done():
            modal_result.set_result(result)

    async with app.run_test() as pilot:
        app._create_background_task(_push_and_wait())
        await pilot.pause()

        # 用 Tab 切换到 Allow 按钮后按回车（避免鼠标坐标问题）
        await pilot.press("tab", "enter")
        await pilot.pause()
        await pilot.pause()

        assert modal_result.done(), (
            "Allow 按钮触发后，背景任务的 _open_modal future 应已完成"
        )
        # Tab 可能聚焦 Allow 或 Deny，关键是模态框被关闭
        assert modal_result.result() in (True, False)
        assert not isinstance(app.screen, PermissionScreen)


@pytest.mark.asyncio
async def test_modal_dismissed_via_escape_key(tmp_path, monkeypatch):
    """场景3：通过 Escape 键关闭模态框（Deny）。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ILLUSION_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))

    app = illusionTerminalApp(api_client=MagicMock())

    modal_result: asyncio.Future = asyncio.get_running_loop().create_future()

    async def _push_and_wait():
        result = await app._open_modal(PermissionScreen("bash", "test reason"))
        if not modal_result.done():
            modal_result.set_result(result)

    async with app.run_test() as pilot:
        app._create_background_task(_push_and_wait())
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()
        await pilot.pause()

        assert modal_result.done(), "Escape 后 future 应已完成"
        assert modal_result.result() is False, (
            f"Escape 应返回 False（Deny），实际: {modal_result.result()}"
        )
        assert not isinstance(app.screen, PermissionScreen)


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="Textual 固有限制：在 App 消息处理器上下文中直接 await modal 会死锁。"
    "bug 修复方式是不在此上下文直接 await，而用 _create_background_task 调度"
    "（见 handle_submit）。此测试验证根因，预期失败。"
)
async def test_modal_deadlock_when_opened_from_sync_handler(tmp_path, monkeypatch):
    """场景4（关键，根因验证）：从 App 消息处理器上下文调用 _open_modal 会死锁。

    模拟 handle_submit 流程：
        @on(Input.Submitted, "#composer")
        async def handle_submit(self, event):
            event.input.value = ""
            await self._process_line(event.value)   # ← 阻塞 App 消息循环
            -> ... -> _ask_permission -> _open_modal -> await future

    死锁机制：
        1. handle_submit 在 App 的 _dispatch_message 中被 await
        2. _open_modal 调用 push_screen(callback=_done) 后 await future
        3. App 消息循环被阻塞在 handle_submit 上
        4. 用户按 y 触发 PermissionScreen.dismiss(True)
        5. dismiss 通过 ResultCallback.__call__ 调用
           self.requester.call_next(self.callback, result)
           将 _done 调度到 App 的 _next_callbacks
        6. App 的 _next_callbacks 无法被刷新（_flush_next_callbacks 在
           _dispatch_message 之后才调用，而 _dispatch_message 阻塞在 handle_submit）
        7. _done 永不执行 -> future 永不 set_result -> handle_submit 永不返回
        8. do_pop() 也无法执行 -> 屏幕不会被视觉替换
        9. 模态框永远停留在 UI 上

    此测试通过 call_later 在 App 上下文中调度一个阻塞协程来模拟 handle_submit。
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ILLUSION_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))

    app = illusionTerminalApp(api_client=MagicMock())

    modal_pushed = asyncio.Event()
    modal_result: asyncio.Future = asyncio.get_running_loop().create_future()

    async def _blocking_handler():
        """模拟 handle_submit：在 App 消息处理上下文中 await _open_modal。"""
        modal_pushed.set()
        result = await app._open_modal(PermissionScreen("bash", "test reason"))
        if not modal_result.done():
            modal_result.set_result(result)

    async with app.run_test() as pilot:
        # 通过 call_later 在 App 的 _next_callbacks 中调度阻塞协程
        # 这模拟了 handle_submit 在 App 消息处理上下文中运行
        app.call_later(_blocking_handler)

        # 等待模态框被 push（_blocking_handler 开始执行并调用了 push_screen）
        await asyncio.wait_for(modal_pushed.wait(), timeout=2.0)
        # 给一点时间让 push_screen 完成
        await asyncio.sleep(0.1)

        # 模态框应该已显示
        assert isinstance(app.screen, PermissionScreen), (
            f"模态框应已显示，实际栈顶: {type(app.screen).__name__}"
        )

        # 尝试按 y 关闭模态框
        await pilot.press("y")

        # 等待一段时间看 future 是否被 set_result
        try:
            await asyncio.wait_for(modal_result, timeout=1.5)
            modal_closed = True
        except asyncio.TimeoutError:
            modal_closed = False

        # 死锁时此断言失败——这正是 bug 的表现
        assert modal_closed, (
            "死锁确认：从 App 消息处理上下文调用 _open_modal 后，"
            "用户按 y 无法关闭模态框。原因：_done 回调被调度到 App 的 "
            "_next_callbacks，但 App 消息循环被阻塞在 handle_submit/"
            "_blocking_handler 中，无法刷新 _next_callbacks，导致 future "
            "永不 set_result，do_pop() 也永不执行。"
        )
