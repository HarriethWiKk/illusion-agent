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

    @pytest.mark.asyncio
    async def test_handle_isolates_handler_exception(self, monkeypatch):
        """测试 handle 捕获处理异常并发 error 事件，不向主循环冒泡（回归：异常拖垮 host）"""
        host = MagicMock()
        host._emit = AsyncMock()
        host._bundle = MagicMock()
        host._bundle.app_state.get.return_value = MagicMock(ui_language="zh-CN")
        dispatcher = WebApiDispatcher(host)

        # 让 handle_web_restore_session 抛异常
        async def boom(request):
            raise RuntimeError("模拟 resume_handler 内部失败")
        monkeypatch.setattr(dispatcher, "handle_web_restore_session", boom)

        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_restore_session", session_id="s1")
        # 不应抛异常
        await dispatcher.handle(req)
        calls = host._emit.call_args_list
        types = [c.args[0].type for c in calls]
        assert "error" in types


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
        host._ws_closed = False  # 模拟 WebSocket 处于连接状态
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


class TestWebNewAndDeleteSession:
    """web_new_session 与 web_delete_sessions 测试"""

    @pytest.fixture
    def dispatcher(self, monkeypatch):
        host = MagicMock()
        host._emit = AsyncMock()
        host._status_snapshot = MagicMock(return_value=MagicMock())
        host._bundle = MagicMock()
        host._bundle.cwd = "/fake/cwd"
        host._bundle.session_id = "old-sid"
        host._bundle.app_state.get.return_value = MagicMock(ui_language="zh-CN")
        dispatcher = WebApiDispatcher(host)
        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._list_session_snapshots", lambda cwd, limit=20: []
        )
        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._delete_session_by_id", lambda cwd, sid: True
        )
        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._state_payload", lambda state: {"model": "test"}
        )
        return dispatcher

    @pytest.mark.asyncio
    async def test_new_session_emits_web_restore_completed_empty(self, dispatcher, monkeypatch):
        """测试新建会话发送空 transcript 的 web_restore_completed"""
        async def fake_new_handler(args, context):
            result = MagicMock()
            result.reset_session = True
            result.message = None
            result.replay_messages = None
            result.restored_session_id = None
            result.should_exit = False
            result.needs_api_rebuild = False
            return result
        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._new_handler", fake_new_handler
        )
        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_new_session")
        await dispatcher.handle(req)
        calls = dispatcher._host._emit.call_args_list
        types = [c.args[0].type for c in calls]
        assert "web_restore_completed" in types

    @pytest.mark.asyncio
    async def test_delete_sessions_emits_web_sessions(self, dispatcher):
        """测试批量删除后推送 web_sessions"""
        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_delete_sessions", session_ids=["s1", "s2"])
        await dispatcher.handle(req)
        calls = dispatcher._host._emit.call_args_list
        types = [c.args[0].type for c in calls]
        assert "web_sessions" in types


class TestWebSetSetting:
    """web_set_setting 统一设置入口测试"""

    @pytest.fixture
    def dispatcher_setting(self, monkeypatch):
        host = MagicMock()
        host._emit = AsyncMock()
        host._status_snapshot = MagicMock(return_value=MagicMock())
        host._bundle = MagicMock()
        host._bundle.cwd = "/fake/cwd"
        host._bundle.app_state.get.return_value = MagicMock(ui_language="zh-CN")
        dispatcher = WebApiDispatcher(host)

        # mock settings 读写：用真实 Settings 实例便于断言字段写入
        fake_settings = MagicMock()
        fake_settings.effort = "medium"
        fake_settings.permission.mode.value = "default"
        fake_settings.ui_language = "zh-CN"
        fake_settings.context_window = 200000
        fake_settings.output_style = "default"
        fake_settings.passes = 1
        fake_settings.model = "env_1.model_1"
        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._load_settings", lambda: fake_settings
        )
        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._save_settings", lambda s: None
        )
        return dispatcher, fake_settings

    @pytest.mark.asyncio
    async def test_set_effort_writes_and_emits(self, dispatcher_setting):
        """测试设置 effort 后写入 settings 并发送 web_setting_changed + state_snapshot"""
        dispatcher, fake_settings = dispatcher_setting
        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_set_setting", setting_key="effort", setting_value="high")
        await dispatcher.handle(req)
        assert fake_settings.effort == "high"
        calls = dispatcher._host._emit.call_args_list
        types = [c.args[0].type for c in calls]
        assert "web_setting_changed" in types

    @pytest.mark.asyncio
    async def test_set_permission_mode_writes(self, dispatcher_setting):
        """测试设置 permission_mode 写入 settings.permission.mode"""
        dispatcher, fake_settings = dispatcher_setting
        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_set_setting", setting_key="permission_mode", setting_value="plan")
        await dispatcher.handle(req)
        assert fake_settings.permission.mode.value == "plan"

    @pytest.mark.asyncio
    async def test_set_unknown_key_emits_error(self, dispatcher_setting):
        """测试未知设置键返回 error"""
        dispatcher, _ = dispatcher_setting
        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_set_setting", setting_key="nonexistent", setting_value="x")
        await dispatcher.handle(req)
        calls = dispatcher._host._emit.call_args_list
        types = [c.args[0].type for c in calls]
        assert "error" in types

    @pytest.mark.asyncio
    async def test_set_permission_mode_with_real_enum(self, monkeypatch):
        """测试设置 permission_mode 使用真实 PermissionMode 枚举（回归 Enum 只读 value 问题）"""
        host = MagicMock()
        host._emit = AsyncMock()
        host._status_snapshot = MagicMock(return_value=MagicMock())
        host._bundle = MagicMock()
        host._bundle.cwd = "/fake/cwd"
        host._bundle.app_state.get.return_value = MagicMock(ui_language="zh-CN")
        dispatcher = WebApiDispatcher(host)

        # 使用真实 Settings 实例（含真实 PermissionMode 枚举）
        from illusion.config.settings import Settings
        real_settings = Settings()
        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._load_settings", lambda: real_settings
        )
        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._save_settings", lambda s: None
        )
        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_set_setting", setting_key="permission_mode", setting_value="plan")
        await dispatcher.handle(req)
        # 验证权限模式确实切换为 plan
        assert real_settings.permission.mode.value == "plan"
        # 验证引擎的权限检查器被更新（回归：旧实现未更新 PermissionChecker）
        host._bundle.engine.set_permission_checker.assert_called_once()
        # 验证发送了 web_setting_changed 而非 error
        calls = host._emit.call_args_list
        types = [c.args[0].type for c in calls]
        assert "web_setting_changed" in types
        assert "error" not in types


class TestWebModels:
    """web_models 推送与 web_request_models 测试"""

    @pytest.fixture
    def dispatcher_models(self):
        host = MagicMock()
        host._emit = AsyncMock()
        host._bundle = MagicMock()
        host._bundle.cwd = "/fake/cwd"
        host._bundle.app_state.get.return_value = MagicMock(ui_language="zh-CN")
        # 复用 ws_host 的 _model_select_options 生成模型选项
        host._model_select_options = MagicMock(return_value=[
            {"value": "env_1.model_1", "label": "M1", "active": True},
        ])
        dispatcher = WebApiDispatcher(host)
        return dispatcher

    @pytest.mark.asyncio
    async def test_request_models_emits_web_models(self, dispatcher_models):
        """测试拉取模型选项发送 web_models 事件"""
        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_request_models")
        await dispatcher_models.handle(req)
        calls = dispatcher_models._host._emit.call_args_list
        models_evts = [c.args[0] for c in calls if c.args[0].type == "web_models"]
        assert len(models_evts) == 1
        assert models_evts[0].web_models[0]["active"] is True


class TestWebResources:
    """web_resources 推送测试"""

    @pytest.mark.asyncio
    async def test_request_resources_emits_web_resources(self, monkeypatch):
        """测试拉取资源发送 web_resources 事件"""
        host = MagicMock()
        host._emit = AsyncMock()
        host._bundle = MagicMock()
        host._bundle.cwd = "/fake/cwd"
        host._bundle.app_state.get.return_value = MagicMock(ui_language="zh-CN")
        dispatcher = WebApiDispatcher(host)

        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._collect_resources",
            lambda bundle: {
                "skills": [{"name": "s1", "description": "d", "source": "project"}],
                "plugins": [],
                "rules": [],
                "mcp_servers": [],
            },
        )
        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_request_resources")
        await dispatcher.handle(req)
        calls = host._emit.call_args_list
        res_evts = [c.args[0] for c in calls if c.args[0].type == "web_resources"]
        assert len(res_evts) == 1
        assert res_evts[0].web_resources["skills"][0]["name"] == "s1"

    @pytest.mark.asyncio
    async def test_push_resources_reuses_collect(self, monkeypatch):
        """测试 _push_resources 复用 _collect_resources"""
        host = MagicMock()
        host._emit = AsyncMock()
        bundle = MagicMock()
        bundle.cwd = "/fake/cwd"
        dispatcher = WebApiDispatcher(host)
        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._collect_resources",
            lambda b: {"skills": [], "plugins": [], "rules": [], "mcp_servers": []},
        )
        await dispatcher._push_resources(bundle)
        assert host._emit.called


class TestWebQuery:
    """web_query B 通道精细化指令测试"""

    @pytest.fixture
    def dispatcher_query(self, monkeypatch):
        host = MagicMock()
        host._emit = AsyncMock()
        host._status_snapshot = MagicMock(return_value=MagicMock())
        host._bundle = MagicMock()
        host._bundle.cwd = "/fake/cwd"
        host._bundle.app_state.get.return_value = MagicMock(ui_language="zh-CN")
        dispatcher = WebApiDispatcher(host)
        return dispatcher

    @pytest.mark.asyncio
    async def test_query_setting_emits_web_query_result(self, dispatcher_query, monkeypatch):
        """测试设置类指令(/passes 3)走 web_query 后返回 web_query_result"""
        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._state_payload", lambda state: {"model": "test"}
        )
        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_query", command="passes", args="3", request_id="r1")
        await dispatcher_query.handle(req)
        calls = dispatcher_query._host._emit.call_args_list
        result_evts = [c.args[0] for c in calls if c.args[0].type == "web_query_result"]
        assert len(result_evts) == 1
        assert result_evts[0].web_request_id == "r1"
        assert result_evts[0].web_query_kind == "text"

    @pytest.mark.asyncio
    async def test_query_unknown_command_emits_result(self, dispatcher_query, monkeypatch):
        """测试未知/执行型指令返回 web_query_result"""
        async def fake_run(line, bundle):
            from illusion.commands.types import CommandResult
            return CommandResult(message="结果文本")
        monkeypatch.setattr(
            "illusion.ui.web.ws_web_api._run_command_via_registry", fake_run
        )
        from illusion.ui.protocol import FrontendRequest
        req = FrontendRequest(type="web_query", command="compact", args="", request_id="r2")
        await dispatcher_query.handle(req)
        calls = dispatcher_query._host._emit.call_args_list
        result_evts = [c.args[0] for c in calls if c.args[0].type == "web_query_result"]
        assert len(result_evts) == 1
        assert result_evts[0].web_query_payload == "结果文本"
