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

import asyncio
import logging
import time as _time
from collections.abc import Awaitable, Callable
from typing import Any

from illusion.commands.registry import create_default_command_registry
from illusion.commands.session import new_handler as _new_handler
from illusion.commands.session import resume_handler as _resume_handler
from illusion.commands.types import CommandContext, CommandResult
from illusion.config.settings import (
    load_settings as _load_settings,
)
from illusion.config.settings import (
    save_settings as _save_settings,
)
from illusion.permissions import PermissionMode
from illusion.services.session_storage import (
    delete_session_by_id as _delete_session_by_id,
)
from illusion.services.session_storage import (
    list_session_snapshots as _list_session_snapshots,
)
from illusion.ui.protocol import BackendEvent, FrontendRequest, _state_payload
from illusion.ui.runtime import RuntimeBundle


def build_replay_items(replay_messages: list[Any] | None) -> list[dict[str, Any]]:
    """将重放消息转换为 TranscriptItem 载荷列表。

    供 WebApiDispatcher.handle_web_restore_session 和
    ws_host.WebBackendHost._restore_session 共用，消除重复逻辑。

    Args:
        replay_messages: ConversationMessage 列表（可能为 None）

    Returns:
        list[Any]: 转录项字典列表（role/text/reasoning/tool_name 等）
    """
    if not replay_messages:
        return []
    from illusion.engine.messages import ToolResultBlock, ToolUseBlock
    from illusion.tasks.types import is_task_notification
    items: list[dict[str, Any]] = []
    # 保存 tool_use_id -> tool_name 的映射
    tool_name_map: dict[str, str] = {}
    for msg in replay_messages:
        if msg.role == "user":
            # 跳过后台任务完成通知：仅注入 LLM，不参与前端重放渲染
            if msg.text.strip() and not is_task_notification(msg.text):
                items.append({"role": "user", "text": msg.text})
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    items.append({
                        "role": "tool_result",
                        "text": block.text_content,
                        "tool_use_id": block.tool_use_id,
                        "tool_name": tool_name_map.get(block.tool_use_id, "tool"),
                        "is_error": block.is_error,
                    })
        elif msg.role == "assistant":
            reasoning = msg.thinking_text.strip()
            assistant_text = msg.text.strip()
            has_tool_use = any(isinstance(b, ToolUseBlock) for b in msg.content)
            if has_tool_use:
                # 添加工具调用信息
                for block in msg.content:
                    if isinstance(block, ToolUseBlock):
                        tool_name_map[block.id] = block.name
                        items.append({
                            "role": "tool",
                            "text": block.name,
                            "tool_name": block.name,
                            "tool_input": block.input,
                            "tool_use_id": block.id,
                        })
                # 保留 reasoning
                if reasoning:
                    items.append({"role": "assistant", "text": "", "reasoning": reasoning})
            elif assistant_text or reasoning:
                item: dict[str, Any] = {"role": "assistant", "text": assistant_text}
                if reasoning:
                    item["reasoning"] = reasoning
                items.append(item)
    return items

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

        所有 handler 异常在此隔离，转译为 error 事件发送给前端，不向主循环冒泡——
        否则任一 web_* 处理异常都会拖垮整个 WebSocket host（表现为后续 emit 报
        "WebSocket write error"）。

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
        try:
            await handler(request)
        except Exception as exc:
            log.exception("处理 web 请求 %s 时发生异常", request.type)
            # 异常隔离：发 error 事件而非冒泡，避免拖垮 host
            try:
                await self._emit(BackendEvent(
                    type="error",
                    message=f"处理 {request.type} 失败: {exc}",
                ))
                # 尝试恢复 busy 态，避免前端卡在 loading
                await self._emit(BackendEvent(type="line_complete"))
            except Exception:
                # 连发 error 都失败时只能记录，不再冒泡
                log.exception("发送 web 异常 error 事件也失败")

    def _dispatch_table(self) -> dict[str, Callable[[FrontendRequest], Awaitable[None]]]:
        """返回请求类型到处理方法的映射表。

        Returns:
            dict[str, Any]: {请求类型字符串: 异步处理方法}
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
        # 同步 app_state（含 context_tokens），使新建会话后右侧栏上下文窗口显示正确（0 tokens）
        from illusion.ui.runtime import sync_app_state
        sync_app_state(bundle)
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

        每个 emit 调用前检查 _ws_closed——WebSocket 已关闭时 _emit 静默返回
        不抛异常，导致 handle() 的 try/except 不触发，前端永远收不到
        web_restore_completed，restoringSessionId 不被清除，页面白屏。

        Args:
            request: 前端请求（session_id 必填）
        """
        bundle = self._host._bundle  # type: ignore[attr-defined]
        if bundle is None:
            await self._emit(BackendEvent(type="error", message="运行时未就绪"))
            return
        session_id = request.session_id or ""

        # WebSocket 已关闭：直接返回，不尝试 emit
        if self._host._ws_closed:  # type: ignore[attr-defined]
            return

        error_msg = None
        replay_items = []

        # 1. 发送恢复开始事件（前端据此显示动画）
        await self._emit(BackendEvent(type="web_restore_started", session_id=session_id))

        # 2. 构建命令上下文并调用 resume_handler
        try:
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
            if result.restored_session_id:
                bundle.session_id = result.restored_session_id
            replay_items = build_replay_items(result.replay_messages)
            # 同步 app_state（含 context_tokens），使 web_restore_completed 的
            # state 快照包含正确的上下文窗口使用量
            from illusion.ui.runtime import sync_app_state
            sync_app_state(bundle)
        except Exception as exc:
            log.exception("恢复会话 %s 失败", session_id)
            error_msg = str(exc)

        # 3. WebSocket 在恢复过程中关闭：跳过 emit，直接返回
        if self._host._ws_closed:  # type: ignore[attr-defined]
            return

        # 4. 始终发 web_restore_completed——前端据此清除 restoringSessionId
        await self._emit(BackendEvent(
            type="web_restore_completed",
            session_id=bundle.session_id,
            items=replay_items,  # type: ignore[arg-type]
            state=_state_payload(bundle.app_state.get()),
            web_error=error_msg,
        ))
        # 5. 推送会话列表刷新
        await self._push_sessions()
        # 6. 发送任务快照与状态快照
        from illusion.tasks import get_task_manager
        await self._emit(BackendEvent.tasks_snapshot(get_task_manager().list_tasks()))
        await self._emit(self._host._status_snapshot())  # type: ignore[attr-defined]

    # _build_replay_items 已提取为模块级函数 build_replay_items()，供本类和 ws_host 共用

    async def handle_web_delete_sessions(self, request: FrontendRequest) -> None:
        """批量删除会话。

        支持指定 session_ids 列表或 delete_all 删除全部。
        当删除当前会话或全部会话时，后端原子化地新建一个空会话并推送
        web_restore_completed，避免前端"先删后建"两阶段逻辑的竞态
        （delete_all 会误删刚建的新会话，导致状态不一致）。

        Args:
            request: 前端请求（session_ids 或 delete_all）
        """
        bundle = self._host._bundle  # type: ignore[attr-defined]
        if bundle is None:
            await self._emit(BackendEvent(type="error", message="运行时未就绪"))
            return
        deleted_current = False
        if request.delete_all:
            sessions = _list_session_snapshots(bundle.cwd, limit=1000)
            # 并行删除：每个 _delete_session_by_id 是同步文件 I/O，用 to_thread 隔离，
            # return_exceptions=True 吞掉单个删除失败，避免一次失败导致整批回滚
            await asyncio.gather(
                *(
                    asyncio.to_thread(_delete_session_by_id, bundle.cwd, s["session_id"])
                    for s in sessions
                ),
                return_exceptions=True,
            )
            deleted_current = True
        elif request.session_ids:
            await asyncio.gather(
                *(
                    asyncio.to_thread(_delete_session_by_id, bundle.cwd, sid)
                    for sid in request.session_ids
                ),
                return_exceptions=True,
            )
            deleted_current = bundle.session_id in request.session_ids
        # 若删除了当前会话或全部会话，后端原子化地新建一个空会话：
        # 清空引擎、切换 session_id 并推送 web_restore_completed（空转录），
        # 使前端主区域即时进入新会话，无需前端编排两阶段删除。
        if deleted_current:
            bundle.engine.clear()
            from uuid import uuid4
            bundle.session_id = uuid4().hex[:12]
            from illusion.ui.runtime import sync_app_state
            sync_app_state(bundle)
            await self._emit(BackendEvent(
                type="web_restore_completed",
                session_id=bundle.session_id,
                items=[],
                state=_state_payload(bundle.app_state.get()),
            ))
        # 删除后推送刷新的会话列表与状态快照
        await self._push_sessions()
        await self._emit(self._host._status_snapshot())  # type: ignore[attr-defined]

    async def handle_web_set_setting(self, request: FrontendRequest) -> None:
        """统一设置标量（A 通道：工具栏/会话控件触发）。

        复用 _apply_setting 私有函数（B 通道的 web_query 设置类指令也调用它），
        设置成功后发送 web_setting_changed + state_snapshot 强同步事件。
        若 key == model 额外发送 web_models 推送。

        Args:
            request: 前端请求（setting_key/setting_value 必填）
        """
        bundle = self._host._bundle  # type: ignore[attr-defined]
        if bundle is None:
            await self._emit(BackendEvent(type="error", message="运行时未就绪"))
            return
        key = request.setting_key or ""
        value = request.setting_value
        ok, error = await self._apply_setting(bundle, key, value)
        if not ok:
            await self._emit(BackendEvent(type="error", message=error or f"设置 {key} 失败"))
            return
        # 1. 发送单项变更事件（前端工具栏即时更新）
        await self._emit(BackendEvent(
            type="web_setting_changed",
            setting_key=key,
            setting_value=value,
        ))
        # 2. 发送完整状态快照（兜底，保证派生字段一致）
        await self._emit(self._host._status_snapshot())  # type: ignore[attr-defined]
        # 3. 若是 model 切换：先推送模型选项让 UI 即时更新 active 态，
        #    再重建 API 客户端（重建可能耗时，如 copilot token 刷新，放最后避免阻塞 UI）
        if key == "model":
            await self._push_models(bundle)
            try:
                from illusion.ui.runtime import _rebuild_api_client
                _rebuild_api_client(bundle, _load_settings())
                # 修复：同时更新 engine 的 model，确保后续请求使用正确的模型名
                new_settings = _load_settings()
                bundle.engine.set_model(new_settings.active_model_name)
            except Exception as exc:
                log.exception("重建 API 客户端失败")
                await self._emit(BackendEvent(
                    type="error",
                    message=f"模型已切换但 API 客户端重建失败: {exc}",
                ))

    async def _apply_setting(self, bundle: RuntimeBundle, key: str, value: Any) -> tuple[bool, str | None]:
        """应用设置到 settings 与 app_state（A/B 通道共用）。

        复用各设置项的写入模式：settings.<field> = value → save_settings →
        app_state.set。model 跨 env 切换时重建 API 客户端。

        Args:
            bundle: 运行时 bundle
            key: 设置键名（effort/permission_mode/model/context_window/
                 ui_language/passes/turns/output_style）
            value: 设置值

        Returns:
            tuple[bool, str | None]: (是否成功, 错误消息)
        """
        settings = _load_settings()
        # 键名 → app_state 字段名映射（settings 字段名可能与 key 不同）
        if key not in (
            "effort", "permission_mode", "model", "context_window",
            "ui_language", "passes", "turns", "output_style",
        ):
            return False, f"不支持的设置键: {key}"

        try:
            if key == "permission_mode":
                # PermissionMode 是枚举，必须整体赋值（.value 只读，不能直接设）
                settings.permission.mode = PermissionMode(str(value))
                _save_settings(settings)
                bundle.app_state.set(permission_mode=settings.permission.mode.value)
                # 更新引擎的权限检查器——引擎初始化时创建的 PermissionChecker 持有旧的
                # PermissionSettings 引用，必须重建并注入，否则计划模式等权限限制不生效
                from illusion.permissions import PermissionChecker
                checker = PermissionChecker(settings.permission)
                checker.sync_sandbox_restrictions(settings.sandbox)
                bundle.engine.set_permission_checker(checker)
            elif key == "turns":
                # turns: unlimited → None，否则 int；影响 engine.max_turns
                turns_val: int | None
                if str(value) == "unlimited":
                    turns_val = None
                else:
                    turns_val = int(value)
                bundle.engine.set_max_turns(turns_val)
            elif key == "model":
                settings.model = str(value)
                _save_settings(settings)
                bundle.app_state.set(model=str(value))
                # 修复：同步更新 settings_overrides，避免 current_settings() 返回缓存的旧值
                bundle.settings_overrides["model"] = str(value)
                # 注：API 客户端重建（_rebuild_api_client）延迟到 emit 之后执行，
                # 避免重建耗时（如 copilot token 刷新）阻塞前端 UI 反馈
            else:
                # effort / context_window / ui_language / passes / output_style
                # settings 字段名与 key 相同（output_style / ui_language / passes / context_window / effort）
                setattr(settings, key, value)
                _save_settings(settings)
                # app_state 字段名与 key 相同
                bundle.app_state.set(**{key: value})
                # 修复：同步更新 settings_overrides，避免 current_settings() 返回缓存的旧值
                if key in ("effort", "model", "max_turns", "base_url", "api_key", "api_format"):
                    bundle.settings_overrides[key] = value
                # 修复：effort 需要同步到 engine，确保后续请求使用正确的 effort 级别
                if key == "effort":
                    from illusion.api.effort import EffortLevel
                    try:
                        bundle.engine.effort = EffortLevel(str(value))
                    except ValueError:
                        log.warning("无效的 effort 值: %s", value)
        except Exception as exc:
            log.exception("应用设置 %s 失败", key)
            return False, f"设置 {key} 失败: {exc}"
        return True, None

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
        options = []
        for s in sessions:
            ts = _time.strftime("%m/%d %H:%M", _time.localtime(s["created_at"]))
            summary = (s.get("summary", "") or ("（无摘要）" if zh else "(no summary)"))[:50]
            turn_count = s.get("turn_count", 0)
            options.append({
                "id": s["session_id"],
                "label": f"{ts}  {turn_count}轮  {summary}",
                "created_at": s["created_at"],
                "message_count": s["message_count"],
                "turn_count": turn_count,
                "summary": s.get("summary", ""),
            })
        await self._emit(BackendEvent(type="web_sessions", web_sessions=options))

    async def handle_web_request_models(self, request: FrontendRequest) -> None:
        """拉取模型选项并发送 web_models 事件。

        Args:
            request: 前端请求（无额外载荷）
        """
        bundle = self._host._bundle  # type: ignore[attr-defined]
        if bundle is None:
            return
        await self._push_models(bundle)

    async def _push_models(self, bundle: RuntimeBundle) -> None:
        """推送模型选项列表（供多处复用）。

        复用 ws_host._model_select_options 生成选项（含 active 态）。

        Args:
            bundle: 运行时 bundle
        """
        settings = bundle.current_settings()
        current_model = settings.active_model_name
        options = self._host._model_select_options(current_model)  # type: ignore[attr-defined]
        await self._emit(BackendEvent(type="web_models", web_models=options))

    async def handle_web_request_resources(self, request: FrontendRequest) -> None:
        """拉取右侧栏资源快照并发送 web_resources 事件。

        Args:
            request: 前端请求（无额外载荷）
        """
        bundle = self._host._bundle  # type: ignore[attr-defined]
        if bundle is None:
            return
        await self._push_resources(bundle)

    async def _push_resources(self, bundle: RuntimeBundle) -> None:
        """推送资源快照（供多处复用）。

        复用 _collect_resources 收集 skills/plugins/rules/mcp_servers，
        废弃旧的命令文本正则解析（_parseSkillsResult 等）。

        Args:
            bundle: 运行时 bundle
        """
        resources = _collect_resources(bundle)
        await self._emit(BackendEvent(type="web_resources", web_resources=resources))

    async def handle_web_query(self, request: FrontendRequest) -> None:
        """B 通道精细化指令处理。

        复用 CommandRegistry 的 handler 拿到 CommandResult，但渲染层映射到
        web_query_result（不产生 command_result 事件）。设置类指令（passes/
        turns/output-style/language）内部调用 _apply_setting，触发与 A 通道相同的
        web_setting_changed + state_snapshot 同步。

        不经过 _process_line/handle_line，避免 transcript_item/hook reload 副作用。

        rewind/context 需要多步选择，仍走 select_request 机制。

        Args:
            request: 前端请求（command/args/request_id 必填）
        """
        bundle = self._host._bundle  # type: ignore[attr-defined]
        if bundle is None:
            await self._emit(BackendEvent(type="error", message="运行时未就绪"))
            return
        command = request.command or ""
        args = request.args or ""
        request_id = request.request_id or ""

        # rewind/context/max-tokens 需要多步选择，仍走 select_request 机制（保留旧 _handle_select_command）
        if command in ("rewind", "context", "max-tokens"):
            await self._host._handle_select_command(command)  # type: ignore[attr-defined]
            return

        # 设置类指令：内部走 _apply_setting（与 A 通道共用写入逻辑，DRY）
        setting_commands = {
            "passes": "passes",
            "turns": "turns",
            "output-style": "output_style",
            "language": "ui_language",
        }
        if command in setting_commands and args:
            key = setting_commands[command]
            tokens = args.split()
            # 参数解析：language set zh-CN → "zh-CN"；passes/turns/output-style → 首个 token
            if command == "language" and len(tokens) >= 2 and tokens[0] == "set":
                value = " ".join(tokens[1:])
            else:
                value = tokens[0] if tokens else ""
            ok, error = await self._apply_setting(bundle, key, value)
            if ok:
                await self._emit(BackendEvent(
                    type="web_setting_changed", setting_key=key, setting_value=value,
                ))
                await self._emit(self._host._status_snapshot())  # type: ignore[attr-defined]
                payload = "已更新"
            else:
                payload = error or "设置失败"
            await self._emit(BackendEvent(
                type="web_query_result", web_request_id=request_id, web_command=command,
                web_query_kind="text", web_query_payload=payload,
            ))
            return

        # 执行型/查询型（compact/export/init 及无参查询）：复用 registry handler
        result = await _run_command_via_registry(f"/{command} {args}".strip(), bundle)
        if result is None:
            # 已通过 select_request 或其他机制处理
            return
        payload = result.message or ""
        await self._emit(BackendEvent(
            type="web_query_result", web_request_id=request_id, web_command=command,
            web_query_kind="text", web_query_payload=payload,
        ))


async def _run_command_via_registry(line: str, bundle: RuntimeBundle) -> CommandResult | None:
    """通过 CommandRegistry 执行命令并返回结果（不经过 handle_line）。

    B 通道（web_query）的执行型/查询型指令复用此函数，避免触发
    transcript_item/hook reload 等 terminal 副作用。

    Args:
        line: 完整命令行（如 "/compact"）
        bundle: 运行时 bundle

    Returns:
        CommandResult | None: 命令结果，None 表示命令未识别或已通过其他机制处理
    """
    registry = create_default_command_registry()
    parsed = registry.lookup(line)
    if parsed is None:
        return None
    command, args = parsed
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
    return await command.handler(args, context)


def _collect_resources(bundle: RuntimeBundle) -> dict[str, Any]:
    """收集右侧栏资源快照（skills/plugins/rules/mcp_servers）。

    直接调用各注册表/管理器的结构化接口，废弃旧的命令文本正则解析
    （_parseSkillsResult / _parsePluginsResult / _parseRulesResult）。

    Args:
        bundle: 运行时 bundle

    Returns:
        dict[str, Any]: {skills, plugins, rules, mcp_servers} 结构化快照
    """
    # skills：从技能注册表读取结构化数据
    from illusion.skills.loader import load_skill_registry
    skill_registry = load_skill_registry(bundle.cwd)
    skills = [
        {"name": s.name, "description": s.description or "", "source": s.source}
        for s in skill_registry.list_skills()
    ]

    # plugins：从当前可见插件读取（复用 bundle.current_plugins）
    plugins = []
    try:
        for plugin in bundle.current_plugins():
            manifest = getattr(plugin, "manifest", None)
            name = getattr(manifest, "name", "") if manifest else ""
            description = getattr(manifest, "description", "") if manifest else ""
            plugins.append({
                "name": name,
                "description": description,
                "enabled": bool(getattr(plugin, "enabled", False)),
                "skill_count": 0,
                "mcp_count": 0,
                "command_count": 0,
            })
    except Exception:
        log.exception("收集插件快照失败")

    # rules：从项目规则目录读取，过滤被权限禁用的规则
    rules = []
    try:
        from illusion.permissions.loader import (
            filter_rules_by_permissions,
            is_rules_disabled,
            load_project_permissions,
        )
        from illusion.skills.loader import get_project_rules_dir
        project_permissions = load_project_permissions(bundle.cwd)
        if not is_rules_disabled(project_permissions):
            rules_dir = get_project_rules_dir(bundle.cwd)
            if rules_dir.exists():
                rule_files = filter_rules_by_permissions(
                    sorted(rules_dir.glob("*.md")), project_permissions
                )
                for path in rule_files:
                    rules.append({"name": path.stem, "source": "project"})
    except Exception:
        log.exception("收集规则快照失败")

    # mcp_servers：复用 mcp_manager 的连接状态
    mcp_servers = []
    try:
        for server in bundle.mcp_manager.list_statuses():
            mcp_servers.append({
                "name": server.name,
                "state": server.state,
                "tool_count": len(server.tools) if hasattr(server, "tools") else 0,
            })
    except Exception:
        log.exception("收集 MCP 服务器快照失败")

    return {"skills": skills, "plugins": plugins, "rules": rules, "mcp_servers": mcp_servers}


__all__ = ["WebApiDispatcher"]
