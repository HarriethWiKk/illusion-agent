""" btw 协议模型测试 """
from __future__ import annotations

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
