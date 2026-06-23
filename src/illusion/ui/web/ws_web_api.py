"""
Web 专属请求分发层模块
======================

本模块实现 WebApiDispatcher，专门处理所有 ``web_*`` 前缀的前端请求类型。
与 ws_host.WebBackendHost 的 terminal 共用路径（submit_line/apply_select_command 等）
隔离，避免 web 端操作与 terminal 端命令流程相互干扰。

设计要点：
    - 持有 host 引用（共享 bundle、emit、状态锁等基础设施）
    - 每类 web_* 请求对应一个 handle_* 方法，保持单一职责
    - 设置类写入复用统一的 _apply_setting 私有函数（DRY）
    - 不经过 handle_line，避免触发 transcript_item/hook reload 等 terminal 副作用

类说明：
    - WebApiDispatcher: Web 专属请求分发器

使用示例：
    >>> dispatcher = WebApiDispatcher(host)
    >>> await dispatcher.handle(request)
"""

from __future__ import annotations

import logging

from illusion.services.session_storage import list_session_snapshots as _list_session_snapshots
from illusion.ui.protocol import BackendEvent, FrontendRequest

log = logging.getLogger(__name__)


class WebApiDispatcher:
    """Web 专属请求分发器。

    处理所有 ``web_*`` 前缀的前端请求。持有 host 引用以复用 bundle、
    emit 写锁、状态快照等基础设施，但请求处理逻辑独立于 terminal 路径。

    Attributes:
        _host: WebBackendHost 实例（提供 bundle/emit/_busy 等访问）
    """

    def __init__(self, host: object) -> None:
        """初始化分发器。

        Args:
            host: WebBackendHost 实例
        """
        self._host = host

    async def handle(self, request: FrontendRequest) -> None:
        """分发 web_* 请求到对应的 handle_* 方法。

        Args:
            request: 前端请求（type 以 web_ 开头）
        """
        handler = self._dispatch_table().get(request.type)
        if handler is None:
            await self._emit(BackendEvent(
                type="error",
                message=f"未实现的 web 请求类型: {request.type}",
            ))
            return
        await handler(request)

    def _dispatch_table(self) -> dict[str, object]:
        """返回请求类型到处理方法的映射表。

        Returns:
            dict: {请求类型字符串: 异步处理方法}
        """
        return {
            "web_new_session": self.handle_web_new_session,
            "web_restore_session": self.handle_web_restore_session,
            "web_delete_sessions": self.handle_web_delete_sessions,
            "web_set_setting": self.handle_web_set_setting,
            "web_request_sessions": self.handle_web_request_sessions,
            "web_request_models": self.handle_web_request_models,
            "web_request_resources": self.handle_web_request_resources,
            "web_query": self.handle_web_query,
        }

    # === emit 辅助：委托给 host ===
    async def _emit(self, event: BackendEvent) -> None:
        """通过 host 发送后端事件。

        Args:
            event: 要发送的后端事件
        """
        await self._host._emit(event)  # type: ignore[attr-defined]

    # === 以下方法在后续 Task 中实现，骨架阶段先返回 error 占位 ===

    async def handle_web_new_session(self, request: FrontendRequest) -> None:
        """新建会话（Task 2.3 实现）。"""
        await self._emit(BackendEvent(type="error", message="web_new_session 尚未实现"))

    async def handle_web_restore_session(self, request: FrontendRequest) -> None:
        """恢复指定会话（Task 2.2 实现）。"""
        await self._emit(BackendEvent(type="error", message="web_restore_session 尚未实现"))

    async def handle_web_delete_sessions(self, request: FrontendRequest) -> None:
        """批量删除会话（Task 2.3 实现）。"""
        await self._emit(BackendEvent(type="error", message="web_delete_sessions 尚未实现"))

    async def handle_web_set_setting(self, request: FrontendRequest) -> None:
        """统一设置标量（Task 3.1 实现）。"""
        await self._emit(BackendEvent(type="error", message="web_set_setting 尚未实现"))

    async def handle_web_request_sessions(self, request: FrontendRequest) -> None:
        """拉取会话列表并推送 web_sessions 事件。

        Args:
            request: 前端请求（limit/offset 可选）
        """
        bundle = self._host._bundle  # type: ignore[attr-defined]
        if bundle is None:
            await self._emit(BackendEvent(type="error", message="运行时未就绪"))
            return
        await self._push_sessions()

    async def _push_sessions(self) -> None:
        """推送会话列表（供多处复用）。

        从 session_storage 读取会话快照，格式化为前端需要的结构后推送。
        """
        bundle = self._host._bundle  # type: ignore[attr-defined]
        if bundle is None:
            return
        locale = str(bundle.app_state.get().ui_language or "zh-CN")
        zh = locale.lower().startswith("zh")
        sessions = _list_session_snapshots(bundle.cwd, limit=20)
        import time as _time
        options = []
        for s in sessions:
            ts = _time.strftime("%m/%d %H:%M", _time.localtime(s["created_at"]))
            summary = (s.get("summary", "") or ("（无摘要）" if zh else "(no summary)"))[:50]
            options.append({
                "id": s["session_id"],
                "label": f"{ts}  {s['message_count']}msg  {summary}",
                "created_at": s["created_at"],
                "message_count": s["message_count"],
                "summary": s.get("summary", ""),
            })
        await self._emit(BackendEvent(type="web_sessions", web_sessions=options))

    async def handle_web_request_models(self, request: FrontendRequest) -> None:
        """拉取模型选项（Task 3.2 实现）。"""
        await self._emit(BackendEvent(type="error", message="web_request_models 尚未实现"))

    async def handle_web_request_resources(self, request: FrontendRequest) -> None:
        """拉取右侧栏资源快照（Task 3.3 实现）。"""
        await self._emit(BackendEvent(type="error", message="web_request_resources 尚未实现"))

    async def handle_web_query(self, request: FrontendRequest) -> None:
        """B 通道精细化指令（Task 4.1 实现）。"""
        await self._emit(BackendEvent(type="error", message="web_query 尚未实现"))


__all__ = ["WebApiDispatcher"]
