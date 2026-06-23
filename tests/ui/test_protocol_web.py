"""Web 专属协议模型测试模块

验证 web_* 请求类型与事件类型的协议定义正确。
"""

import pytest
from illusion.ui.protocol import FrontendRequest, BackendEvent


class TestWebFrontendRequest:
    """web_* 前端请求类型测试"""

    def test_web_new_session_request(self):
        """测试 web_new_session 请求可构造"""
        req = FrontendRequest(type="web_new_session")
        assert req.type == "web_new_session"

    def test_web_restore_session_request(self):
        """测试 web_restore_session 请求携带 session_id"""
        req = FrontendRequest(type="web_restore_session", session_id="abc123")
        assert req.type == "web_restore_session"
        assert req.session_id == "abc123"

    def test_web_set_setting_request(self):
        """测试 web_set_setting 请求携带 key/value"""
        req = FrontendRequest(type="web_set_setting", setting_key="effort", setting_value="high")
        assert req.setting_key == "effort"
        assert req.setting_value == "high"

    def test_web_delete_sessions_request(self):
        """测试 web_delete_sessions 请求携带 ids"""
        req = FrontendRequest(type="web_delete_sessions", session_ids=["id1", "id2"])
        assert req.session_ids == ["id1", "id2"]

    def test_web_delete_all_request(self):
        """测试 web_delete_sessions 的 all 标志"""
        req = FrontendRequest(type="web_delete_sessions", delete_all=True)
        assert req.delete_all is True

    def test_web_query_request(self):
        """测试 web_query 请求携带 command/args/request_id"""
        req = FrontendRequest(
            type="web_query",
            command="rewind",
            args="",
            request_id="req-1",
        )
        assert req.command == "rewind"
        assert req.request_id == "req-1"
