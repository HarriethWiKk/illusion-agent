"""WebApiDispatcher 单元测试模块

验证 Web 专属请求分发器能正确路由 web_* 请求。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from illusion.ui.web.ws_web_api import WebApiDispatcher


class TestWebApiDispatcherRouting:
    """WebApiDispatcher 请求路由测试"""

    @pytest.fixture
    def dispatcher(self):
        """创建带 mock emit 的分发器"""
        host = MagicMock()
        host._emit = AsyncMock()
        host._bundle = MagicMock()
        dispatcher = WebApiDispatcher(host)
        return dispatcher

    def test_dispatcher_constructable(self, dispatcher):
        """测试分发器可构造并持有 host 引用"""
        assert dispatcher._host is not None

    @pytest.mark.asyncio
    async def test_handle_unknown_web_request_emits_error(self, dispatcher):
        """测试未实现的 web_ 请求类型优雅返回 error 事件，不抛异常"""
        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_request_sessions")
        # 暂未实现的请求应优雅返回 error，不抛异常
        await dispatcher.handle(req)
        # handle 内部应调用 host._emit 发送 error 或对应事件
        assert dispatcher._host._emit.called


class TestWebHostDispatch:
    """ws_host 主循环分发 web_* 请求到 WebApiDispatcher 测试"""

    def test_host_holds_web_api_dispatcher(self):
        """测试 WebBackendHost 实例持有 _web_api 属性"""
        from illusion.ui.web.ws_host import WebBackendHost, WebHostConfig
        host = WebBackendHost(WebHostConfig(model="test-model"), MagicMock())
        assert hasattr(host, "_web_api")
        assert host._web_api is not None


class TestWebRequestSessions:
    """web_request_sessions 会话列表拉取测试"""

    @pytest.fixture
    def dispatcher_with_bundle(self, monkeypatch):
        """创建带 mock bundle 和 session_storage 的分发器"""
        host = MagicMock()
        host._emit = AsyncMock()
        host._bundle = MagicMock()
        host._bundle.cwd = "/fake/cwd"
        host._bundle.app_state.get.return_value = MagicMock(ui_language="zh-CN")
        dispatcher = WebApiDispatcher(host)

        # mock session_storage.list_session_snapshots
        fake_sessions = [
            {"session_id": "s1", "created_at": 1700000000, "message_count": 5, "summary": "测试会话1"},
            {"session_id": "s2", "created_at": 1700000100, "message_count": 3, "summary": "测试会话2"},
        ]
        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._list_session_snapshots",
            lambda cwd, limit=20: fake_sessions,
        )
        return dispatcher

    @pytest.mark.asyncio
    async def test_request_sessions_emits_web_sessions(self, dispatcher_with_bundle):
        """测试拉取会话列表后发送 web_sessions 事件"""
        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_request_sessions")
        await dispatcher_with_bundle.handle(req)
        calls = dispatcher_with_bundle._host._emit.call_args_list
        emitted_types = [c.args[0].type for c in calls]
        assert "web_sessions" in emitted_types
        # 验证 web_sessions 载荷结构
        sessions_evt = next(c.args[0] for c in calls if c.args[0].type == "web_sessions")
        assert len(sessions_evt.web_sessions) == 2
        assert sessions_evt.web_sessions[0]["id"] == "s1"


class TestWebRestoreSession:
    """web_restore_session 零 suppress 恢复流程测试"""

    @pytest.fixture
    def dispatcher_restore(self, monkeypatch):
        """创建带 mock 恢复流程的分发器"""
        host = MagicMock()
        host._emit = AsyncMock()
        host._status_snapshot = MagicMock(return_value=MagicMock())
        host._bundle = MagicMock()
        host._bundle.cwd = "/fake/cwd"
        host._bundle.session_id = "old-sid"
        host._bundle.app_state.get.return_value = MagicMock(ui_language="zh-CN")
        dispatcher = WebApiDispatcher(host)

        # mock resume_handler 返回带 restored_session_id 和 replay_messages 的结果
        async def fake_resume_handler(args, context):
            result = MagicMock()
            result.restored_session_id = "restored-sid"
            result.replay_messages = []
            result.message = None
            result.reset_session = False
            result.should_exit = False
            result.needs_api_rebuild = False
            return result

        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._resume_handler", fake_resume_handler
        )
        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._list_session_snapshots", lambda cwd, limit=20: []
        )
        # mock _state_payload
        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._state_payload", lambda state: {"model": "test"}
        )
        return dispatcher

    @pytest.mark.asyncio
    async def test_restore_emits_started_and_completed(self, dispatcher_restore):
        """测试恢复流程发送 web_restore_started 与 web_restore_completed"""
        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_restore_session", session_id="s1")
        await dispatcher_restore.handle(req)
        calls = dispatcher_restore._host._emit.call_args_list
        types = [c.args[0].type for c in calls]
        assert "web_restore_started" in types
        assert "web_restore_completed" in types
        # web_restore_completed 必须携带 state 快照
        completed = next(c.args[0] for c in calls if c.args[0].type == "web_restore_completed")
        assert completed.state is not None
        assert completed.session_id == "restored-sid"

    @pytest.mark.asyncio
    async def test_restore_no_select_request_or_command_result(self, dispatcher_restore):
        """测试恢复流程不产生 select_request/command_result（零 suppress 保证）"""
        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_restore_session", session_id="s1")
        await dispatcher_restore.handle(req)
        calls = dispatcher_restore._host._emit.call_args_list
        types = [c.args[0].type for c in calls]
        assert "select_request" not in types
        assert "command_result" not in types
