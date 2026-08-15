""" btw 协议模型测试 """
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from illusion.ui.backend_host import ReactBackendHost
from illusion.ui.protocol import BackendEvent, FrontendRequest


def test_btw_request_parse():
    req = FrontendRequest(type="btw_request", question="hi", request_id="r1")
    assert req.type == "btw_request"
    assert req.question == "hi"
    assert req.request_id == "r1"


def test_btw_cancel_parse():
    req = FrontendRequest(type="btw_cancel", request_id="r1")
    assert req.type == "btw_cancel"


def test_btw_response_event():
    ev = BackendEvent(type="btw_response", request_id="r1", reply="42")
    assert ev.type == "btw_response"
    assert ev.reply == "42"
    assert ev.request_id == "r1"


def test_btw_response_error():
    ev = BackendEvent(type="btw_response", request_id="r1", error="boom")
    assert ev.error == "boom"


@pytest.mark.asyncio
async def test_btw_request_dispatches_to_handler(monkeypatch, tmp_path):
    """btw_request 被路由到 _handle_btw_request 并返回 btw_response。"""
    host = ReactBackendHost.__new__(ReactBackendHost)
    # 根据实际属性名设置 mock
    host._btw_tasks = {}
    host._dispatch_tasks = set()
    host._bundle = MagicMock()
    host._bundle.cwd = str(tmp_path)
    host._bundle.engine = MagicMock()

    captured = {}

    async def fake_emit(ev):
        captured["ev"] = ev

    host._emit = fake_emit

    async def fake_run(question, engine, app_state=None):
        return "42"

    monkeypatch.setattr("illusion.ui.backend_host.run_side_question", fake_run)

    req = FrontendRequest(type="btw_request", question="q", request_id="r1")
    await host._handle_btw_request(req)
    # 等待后台任务完成，确保 emit 已执行
    task = host._btw_tasks.get("r1")
    if task is not None:
        await task

    assert captured["ev"].type == "btw_response"
    assert captured["ev"].reply == "42"
    assert captured["ev"].request_id == "r1"


@pytest.mark.asyncio
async def test_btw_cancel_aborts_running_task():
    """btw_cancel 取消进行中的侧问任务。"""
    host = ReactBackendHost.__new__(ReactBackendHost)
    host._btw_tasks = {}
    fake_task = MagicMock()
    fake_task.cancel = MagicMock()
    host._btw_tasks["r1"] = fake_task

    captured = {}

    async def fake_emit(ev):
        captured["ev"] = ev

    host._emit = fake_emit

    await host._handle_btw_cancel(FrontendRequest(type="btw_cancel", request_id="r1"))
    fake_task.cancel.assert_called_once()
    assert "r1" not in host._btw_tasks
