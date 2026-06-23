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
