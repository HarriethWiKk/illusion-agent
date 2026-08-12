"""ws_host select_command 路由测试。

覆盖 Task 3.1：
    - max-tokens 命令经 WebApiDispatcher.handle_web_query 委托给 _handle_select_command
    - context-window __custom__ 不再发射 error 事件，静默返回 line_complete
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from illusion.ui.protocol import BackendEvent, FrontendRequest
from illusion.ui.web.ws_host import WebBackendHost
from illusion.ui.web.ws_web_api import WebApiDispatcher
from illusion.utils.aioqueue import Queue


def _make_host(**fields: Any) -> WebBackendHost:
    """绕过 __init__ 构造 host，仅设置测试所需字段。

    复用 tests/test_ui/test_web_host_refactored.py 的模式：用 object.__new__
    绕过 WebHostConfig + WebSocket 依赖，手动注入 _apply_select_command 测试
    所访问的字段（_emit / _bundle 等）。
    """
    host = object.__new__(WebBackendHost)
    defaults: dict[str, Any] = {
        "_config": None,
        "_websocket": MagicMock(),
        "_bundle": None,
        "_sessions": {},
        "_active_session_id": None,
        "_write_queue": Queue(),
        "_write_task": None,
        "_dispatch_tasks": set(),
        "_request_queue": asyncio.Queue(),
        "_permission_requests": {},
        "_question_requests": {},
        "_session_allowed_tools": set(),
        "_running": True,
        "_ws_closed": False,
        "_periodic_task": None,
    }
    defaults.update(fields)
    for key, value in defaults.items():
        setattr(host, key, value)
    return host


@pytest.mark.asyncio
async def test_max_tokens_routes_to_select_command():
    """web_query 的 max-tokens 命令应委托给 _handle_select_command（会话级）。"""
    host = MagicMock()
    host._emit = AsyncMock()
    host._bundle = MagicMock()  # 非 None，绕过 bundle 检查
    host._handle_select_command = AsyncMock()
    session = MagicMock()
    session.session_id = "s1"
    session.bundle = MagicMock()
    host._resolve_session = MagicMock(return_value=session)
    dispatcher = WebApiDispatcher(host)

    req = FrontendRequest(
        type="web_query",
        command="max-tokens",
        args="",
        request_id="test",
    )
    await dispatcher.handle_web_query(req)

    host._resolve_session.assert_called_once_with(None)
    host._handle_select_command.assert_awaited_once_with("max-tokens", session)


@pytest.mark.asyncio
async def test_context_window_custom_does_not_emit_error():
    """context-window __custom__ 不应发射 error 事件。"""
    emitted_events: list[BackendEvent] = []

    async def fake_emit(event: BackendEvent, **kwargs: Any) -> None:
        # 模拟真实 _emit 的会话标记逻辑
        sid = kwargs.get("session_id")
        if sid:
            event.session_id = sid
        emitted_events.append(event)

    host = _make_host()
    host._emit = fake_emit  # type: ignore[assignment]
    session = MagicMock()
    session.session_id = "s1"
    session.rewind_target_idx = None
    session.current_request_id = None

    await host._apply_select_command(session, "context-window", "__custom__")

    # 不应有 type=error 事件
    assert not any(e.type == "error" for e in emitted_events)
    # 应发射 line_complete 提示前端关闭选择框（携带会话 ID）
    line_completes = [e for e in emitted_events if e.type == "line_complete"]
    assert line_completes
    assert line_completes[0].session_id == "s1"
