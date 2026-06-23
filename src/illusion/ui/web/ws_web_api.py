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

from illusion.commands.session import resume_handler as _resume_handler
from illusion.commands.session import new_handler as _new_handler
from illusion.commands.types import CommandContext
from illusion.services.session_storage import (
    delete_session_by_id as _delete_session_by_id,
    list_session_snapshots as _list_session_snapshots,
)
from illusion.ui.protocol import BackendEvent, FrontendRequest, _state_payload

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
        """新建会话。

        复用 new_handler 重置会话状态，然后发送空的 web_restore_completed
        让前端清空主区域。

        Args:
            request: 前端请求（无额外载荷）
        """
        bundle = self._host._bundle  # type: ignore[attr-defined]
        if bundle is None:
            await self._emit(BackendEvent(type="error", message="运行时未就绪"))
            return
        context = CommandContext(
            engine=bundle.engine,
            hooks_summary=bundle.hook_summary(),
            mcp_summary=bundle.mcp_summary(),
            plugin_summary=bundle.plugin_summary(),
            cwd=bundle.cwd,
            tool_registry=bundle.tool_registry,
            app_state=bundle.app_state,
            session_id=bundle.session_id,
        )
        await _new_handler("", context)
        # new_handler 内部已重置会话，此处重新生成 session_id 保持一致
        from uuid import uuid4
        bundle.session_id = uuid4().hex[:12]
        # 发送空 transcript 的恢复完成事件，前端据此清空主区域
        await self._emit(BackendEvent(
            type="web_restore_completed",
            session_id=bundle.session_id,
            items=[],
            state=_state_payload(bundle.app_state.get()),
        ))
        await self._push_sessions()
        await self._emit(self._host._status_snapshot())  # type: ignore[attr-defined]

    async def handle_web_restore_session(self, request: FrontendRequest) -> None:
        """恢复指定会话（零 suppress 流程）。

        直接调用 resume_handler，不经过 handle_line，避免触发
        select_request/command_result/transcript_item 等 terminal 副作用。
        通过 web_restore_started/completed 显式标注，前端据此显示加载动画。

        Args:
            request: 前端请求（session_id 必填）
        """
        bundle = self._host._bundle  # type: ignore[attr-defined]
        if bundle is None:
            await self._emit(BackendEvent(type="error", message="运行时未就绪"))
            return
        session_id = request.session_id or ""
        # 1. 发送恢复开始事件（前端据此显示动画）
        await self._emit(BackendEvent(type="web_restore_started", session_id=session_id))
        # 2. 构建命令上下文并调用 resume_handler
        context = CommandContext(
            engine=bundle.engine,
            hooks_summary=bundle.hook_summary(),
            mcp_summary=bundle.mcp_summary(),
            plugin_summary=bundle.plugin_summary(),
            cwd=bundle.cwd,
            tool_registry=bundle.tool_registry,
            app_state=bundle.app_state,
            session_id=bundle.session_id,
        )
        result = await _resume_handler(session_id, context)
        # 3. 处理恢复结果：更新 session_id
        if result.restored_session_id:
            bundle.session_id = result.restored_session_id
        # 4. 构建 replay_items（复用消息转换逻辑）
        replay_items = self._build_replay_items(result.replay_messages)
        # 5. 发送恢复完成事件（携带完整 state 快照，前端据此同步工具栏）
        # replay_items 是字典列表，BackendEvent.items 为 list[TranscriptItem]，
        # pydantic 会自动校验转换
        await self._emit(BackendEvent(
            type="web_restore_completed",
            session_id=bundle.session_id,
            items=replay_items,
            state=_state_payload(bundle.app_state.get()),
        ))
        # 6. 推送会话列表刷新
        await self._push_sessions()
        # 7. 发送任务快照与状态快照
        from illusion.tasks import get_task_manager
        await self._emit(BackendEvent.tasks_snapshot(get_task_manager().list_tasks()))
        await self._emit(self._host._status_snapshot())  # type: ignore[attr-defined]

    def _build_replay_items(self, replay_messages: list | None) -> list:
        """将重放消息转换为 TranscriptItem 载荷列表。

        复用 ws_host._restore_session 中的转换逻辑，确保恢复后的转录项
        与正常对话流格式一致。

        Args:
            replay_messages: ConversationMessage 列表（可能为 None）

        Returns:
            list: 转录项字典列表
        """
        if not replay_messages:
            return []
        from illusion.engine.messages import ToolUseBlock, ToolResultBlock
        tool_uses_by_id: dict[str, dict] = {}
        items: list[dict] = []
        for msg in replay_messages:
            if msg.role == "user":
                if msg.text.strip():
                    items.append({"role": "user", "text": msg.text})
                for block in msg.content:
                    if isinstance(block, ToolResultBlock):
                        tool_info = tool_uses_by_id.get(block.tool_use_id, {})
                        items.append({
                            "role": "tool_result",
                            "text": block.text_content,
                            "tool_name": tool_info.get("name"),
                            "tool_use_id": block.tool_use_id,
                            "is_error": block.is_error,
                        })
            elif msg.role == "assistant":
                reasoning = msg.thinking_text.strip()
                assistant_text = msg.text.strip()
                has_tool_use = any(isinstance(b, ToolUseBlock) for b in msg.content)
                if not has_tool_use and (assistant_text or reasoning):
                    item = {"role": "assistant", "text": assistant_text}
                    if reasoning:
                        item["reasoning"] = reasoning
                    items.append(item)
        return items

    async def handle_web_delete_sessions(self, request: FrontendRequest) -> None:
        """批量删除会话。

        支持指定 session_ids 列表或 delete_all 删除全部。

        Args:
            request: 前端请求（session_ids 或 delete_all）
        """
        bundle = self._host._bundle  # type: ignore[attr-defined]
        if bundle is None:
            await self._emit(BackendEvent(type="error", message="运行时未就绪"))
            return
        if request.delete_all:
            sessions = _list_session_snapshots(bundle.cwd, limit=1000)
            for s in sessions:
                _delete_session_by_id(bundle.cwd, s["session_id"])
        elif request.session_ids:
            for sid in request.session_ids:
                _delete_session_by_id(bundle.cwd, sid)
        # 删除后推送刷新的会话列表
        await self._push_sessions()

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
