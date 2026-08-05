"""
Web 后端主机模块
===============

本模块实现基于 WebSocket 协议的后端主机，用于与 Web 前端通信。

主要功能：
    - 基于 WebSocket 的 JSON 协议通信
    - 命令处理（/env, /resume, /permissions 等）
    - 权限确认和工作流管理
    - 会话状态快照
    - 任务管理快照
    - MCP 服务器状态管理

类说明：
    - WebHostConfig: Web 后端主机配置数据类
    - WebBackendHost: Web 后端主机实现类

使用示例：
    >>> from illusion.ui.web.ws_host import WebBackendHost, WebHostConfig
    >>> from fastapi import WebSocket
    >>> config = WebHostConfig(model="claude-sonnet-4-20250514")
    >>> host = WebBackendHost(config, websocket)
    >>> await host.run()
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from illusion.api.client import SupportsStreamingMessages
from illusion.auth.manager import AuthManager
from illusion.coordinator.agent_definitions import get_all_agent_definitions
from illusion.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    ErrorEvent,
    StatusEvent,
    StreamEvent,
    ToolChainCompleted,
    ToolChainStarted,
    ToolExecutionCompleted,
    ToolExecutionStarted,
    ToolProgressEvent,
)
from illusion.output_styles import load_output_styles
from illusion.services.agent_creator import (
    generate_agent_from_description,
    list_available_models,
    list_available_tools,
    validate_agent_definition,
    write_agent_definition,
)
from illusion.services.side_question import SideQuestionError, run_side_question
from illusion.tasks import get_task_manager
from illusion.tasks.types import is_task_notification
from illusion.ui.permission_store import add_always_allowed_tool, load_always_allowed_tools
from illusion.ui.protocol import (
    BackendEvent,
    FrontendRequest,
    TranscriptItem,
    format_permission_mode,
)
from illusion.ui.runtime import (
    RuntimeBundle,
    _wrap_in_system_reminder,
    build_runtime,
    close_runtime,
    handle_background_completions,
    handle_line,
    start_runtime,
    sync_app_state,
)
from illusion.utils.aioqueue import Queue, QueueShutDown

# 配置模块级日志记录器
log = logging.getLogger(__name__)


def _strip_tool_previews(text: str, tool_uses: list[Any] | None) -> str:
    """从助手文本中移除工具预览行。

    使用实际工具名称精确匹配，不依赖前导空格数量。
    """
    if not tool_uses:
        return text
    names = [re.escape(tu.name) for tu in tool_uses]
    pattern = re.compile(rf"^\s*(?:{'|'.join(names)})\s*\(", re.IGNORECASE)
    lines = text.split("\n")
    filtered = [line for line in lines if not pattern.match(line)]
    return "\n".join(filtered) if filtered else text


@dataclass(frozen=True)
class WebHostConfig:
    """Web 后端主机配置数据类。

    Attributes:
        model: 使用的模型名称
        max_turns: 最大对话轮次
        base_url: API 基础 URL
        system_prompt: 系统提示词
        api_key: API 密钥
        api_format: API 格式（openai/anthropic）
        api_client: 流式 API 客户端实例
        restore_messages: 恢复的会话消息列表
        restore_session_id: 恢复的会话 ID
        enforce_max_turns: 是否强制限制最大轮次
        effort: 推理强度级别（low/medium/high/xhigh/max）
    """

    model: str | None = None
    max_turns: int | None = None
    base_url: str | None = None
    system_prompt: str | None = None
    api_key: str | None = None
    api_format: str | None = None
    api_client: SupportsStreamingMessages | None = None
    restore_messages: list[dict[str, Any]] | None = None
    restore_session_id: str | None = None
    enforce_max_turns: bool = True
    effort: str | None = None
    # 渠道感知：与 illusion 主命令一致，注入渠道提示词和跨渠道工具
    channel_hint: str | None = None
    channel_tools: list[Any] | None = None


class WebBackendHost:
    """Web 后端主机。

    通过 WebSocket 协议与 Web 前端通信，驱动 IllusionAgent 运行时。
    处理所有前端请求并发送后端事件。

    Attributes:
        _config: Web 后端配置
        _websocket: WebSocket 连接实例
        _bundle: 运行时数据 bundle
        _write_queue: 写入事件队列（串行化所有 WebSocket 写入）
        _write_task: 单一消费者写循环 Task
        _dispatch_tasks: fire-and-forget task 强引用集合
        _request_queue: 请求队列
        _permission_requests: 权限请求字典（request_id -> Future[Any]）
        _question_requests: 用户问答请求字典
        _always_allowed_tools: "总是允许"的工具集合
        _busy: 当前是否正在处理请求
        _running: 是否正在运行
        _ws_closed: WebSocket 是否已关闭
        _active_line_task: 当前活动的行处理任务
        _periodic_task: 周期状态更新 Task
        _last_tool_inputs: 每个工具名称的最后输入（用于富事件发射）
    """

    def __init__(self, config: WebHostConfig, websocket: WebSocket) -> None:
        self._config = config
        self._websocket = websocket
        self._bundle: RuntimeBundle | None = None
        self._write_queue: Queue[BackendEvent] = (
            Queue()
        )  # 替代 _write_lock，串行化所有 WebSocket 写入
        self._write_task: asyncio.Task[None] | None = None  # 单一消费者写循环 Task
        self._dispatch_tasks: set[asyncio.Task[None]] = set()  # fire-and-forget 强引用集合
        self._request_queue: asyncio.Queue[FrontendRequest] = asyncio.Queue()
        self._permission_requests: dict[str, asyncio.Future[bool]] = {}  # 权限请求
        self._question_requests: dict[str, asyncio.Future[str | dict[Any, Any]]] = {}  # 用户问答
        self._always_allowed_tools: set[str] = set()  # 总是允许的工具
        self._busy = False  # 忙碌状态
        self._running = True  # 运行状态
        self._ws_closed = False  # WebSocket 是否已关闭
        self._active_line_task: asyncio.Task[bool] | None = None  # 当前任务
        self._periodic_task: asyncio.Task[None] | None = None  # 周期状态更新 Task
        # modal 串行化锁：前端 modal 是单例，并发 modal_request 会互相覆盖导致
        # 第一个 future 永不 resolve。所有 modal 请求（permission/question/plan）
        # 必须串行执行，前一个完成释放锁后下一个才能发送 modal_request。
        self._modal_lock: asyncio.Lock = asyncio.Lock()
        # 跟踪每个工具名称的最后输入，用于富事件发射
        self._last_tool_inputs: dict[str, dict[str, Any]] = {}
        # 跟踪已发送 tool_started 事件的工具调用ID，避免重复显示
        self._emitted_tool_started_ids: set[str] = set()
        # 当前 apply_select_command 的请求 ID，用于 command_result 精确匹配
        self._current_request_id: str | None = None
        # btw 侧问任务映射：request_id -> asyncio.Task，支持 btw_cancel 取消
        self._btw_tasks: dict[str, asyncio.Task[None]] = {}
        # Web 专属请求分发器（处理 web_* 前缀请求，与 terminal 路径隔离）
        from illusion.ui.web.ws_web_api import WebApiDispatcher

        self._web_api = WebApiDispatcher(self)

    async def run(self) -> int:
        """运行后端主机主循环。"""
        # 构建运行时环境
        try:
            self._bundle = await build_runtime(
                model=self._config.model,
                max_turns=self._config.max_turns,
                base_url=self._config.base_url,
                system_prompt=self._config.system_prompt,
                api_key=self._config.api_key,
                api_format=self._config.api_format,
                api_client=self._config.api_client,
                restore_messages=self._config.restore_messages,
                restore_session_id=self._config.restore_session_id,
                permission_prompt=self._ask_permission,
                ask_user_prompt=self._ask_question,  # type: ignore[arg-type]
                plan_approval_prompt=self._ask_plan_approval,
                effort=self._config.effort,
                channel_hint=self._config.channel_hint,
                channel_tools=self._config.channel_tools,
            )
        except Exception as exc:
            log.exception("Failed to build runtime")
            await self._emit(BackendEvent(type="error", message=str(exc)))
            return 1
        assert self._bundle is not None
        await start_runtime(self._bundle)
        # 首次进入主动 sync，避免 context_window 为 0
        sync_app_state(self._bundle)
        # 加载总是允许的工具列表
        self._always_allowed_tools = load_always_allowed_tools(self._bundle.cwd)

        # 包装 on_task_complete：后台任务完成后发送 tasks_snapshot，
        # 并在主循环空闲时自动进入 busy 处理积压的完成通知。
        # （runtime.build_runtime 内部注册的原回调仅通知 bg_agent_tracker，
        #   不会驱动 host 恢复主循环，导致空闲期后台完成无人消费。）
        _task_manager = get_task_manager()
        _original_on_task_complete = _task_manager.on_task_complete

        def _wrapped_on_task_complete(task_id: str, task: Any) -> None:
            # 先调用原回调（通知 bg_agent_tracker）
            if _original_on_task_complete is not None:
                _original_on_task_complete(task_id, task)
            # 异步发送 tasks_snapshot，让前端 statusBar 立即更新
            self._create_background_task(
                self._emit(BackendEvent.tasks_snapshot(_task_manager.list_tasks()))
            )
            # 后台任务完成且主循环空闲 → 自动进入 busy 处理积压通知
            if not self._busy and self._bundle is not None:
                tracker = self._bundle.engine._bg_agent_tracker
                if tracker is not None and tracker.has_completions():
                    self._create_background_task(self._auto_resume_bg())

        _task_manager.on_task_complete = _wrapped_on_task_complete

        # 启动写循环（单一消费者，串行化所有 WebSocket 写入）
        self._write_task = asyncio.create_task(self._write_loop())
        # 发送就绪事件
        # 计算首次登录标识（无 env_N 且无 working_directory），前端据此自动弹出配置表单
        from illusion.cli.workspace import is_first_login
        from illusion.config.settings import load_settings
        _first_login = is_first_login(load_settings())
        await self._emit(
            BackendEvent.ready(
                self._bundle.app_state.get(),
                get_task_manager().list_tasks(),
                [f"/{command.name}" for command in self._bundle.commands.list_commands()],
                first_login=_first_login,
            )
        )
        # 发送状态快照
        await self._emit(self._status_snapshot())
        # Web 前端专属：ready 后推送会话列表（替代旧 list_sessions setTimeout hack）
        await self._web_api._push_sessions()
        # Web 前端专属：ready 后推送资源与模型选项（替代旧 setTimeout 串行发指令 hack）
        await self._web_api._push_resources(self._bundle)
        await self._web_api._push_models(self._bundle)

        # 创建请求读取任务
        reader = asyncio.create_task(self._read_requests())

        # 创建定期状态更新任务（每秒刷新一次，用于 agent 计数等实时状态）
        async def _periodic_status_update() -> None:
            while self._running and not self._ws_closed:
                await asyncio.sleep(1.0)
                if self._running and not self._ws_closed and self._bundle is not None:
                    await self._emit(self._status_snapshot())

        self._periodic_task = asyncio.create_task(_periodic_status_update())

        try:
            # 主循环：处理请求
            while self._running:
                request = await self._request_queue.get()
                try:
                    should_continue = await self._dispatch_request(request)
                except asyncio.CancelledError:
                    # 主循环自身被取消（如 uvicorn shutdown / disconnect 关闭路径）：
                    # 必须重新抛出。asyncio 取消是"一次性"的，吞掉后下一次
                    # _request_queue.get() 会永久阻塞，后端无法退出。
                    # （行任务取消由 reader 的 stop 分支直接处理，不会到达此处。）
                    raise
                except Exception:
                    # 请求级异常不应拖垮后端进程（与 backend_host 主循环同理）：
                    # 未捕获异常会让进程异常退出，Windows 上解释器 shutdown 期间
                    # daemon 线程竞争 stdio 缓冲锁会触发原生崩溃（0xC0000005）。
                    log.exception("处理请求异常: type=%s", request.type)
                    should_continue = True
                    try:
                        await self._emit(BackendEvent(type="error", message="Internal error, please retry"))
                        await self._emit(BackendEvent(type="line_complete"))
                    except Exception:
                        log.exception("发送错误事件失败")
                if not should_continue:
                    break
        finally:
            # 清理资源：取消 reader，_shutdown 处理其余 task/队列，最后关闭运行时
            reader.cancel()
            try:
                await reader
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("读取任务关闭异常")
            await self._shutdown()
            if self._bundle is not None:
                await close_runtime(self._bundle)
        return 0

    async def _dispatch_request(self, request: FrontendRequest) -> bool:
        """处理单个前端请求。

        Args:
            request: 前端请求

        Returns:
            bool: 是否继续主循环（False 表示请求要求关闭后端）
        """
        # Web 前端专属请求：委托给 WebApiDispatcher（与 terminal 路径隔离）
        if request.type.startswith("web_"):
            await self._web_api.handle(request)
            return True
        # 关闭请求
        if request.type == "shutdown":
            await self._emit(BackendEvent(type="shutdown"))
            return False
        # 停止当前任务
        if request.type == "stop":
            await self._stop_active_line()
            return True
        # 权限响应
        if request.type == "permission_response":
            if request.request_id in self._permission_requests:
                self._permission_requests[request.request_id].set_result(
                    bool(request.allowed)
                )
            # 记住"总是允许"工具
            if request.always_allow and request.tool_name:
                self._always_allowed_tools.add(request.tool_name)
                if self._bundle is not None:
                    self._always_allowed_tools = add_always_allowed_tool(
                        self._bundle.cwd,
                        request.tool_name,
                    )
            await self._emit(BackendEvent(type="modal_request", modal=None))
            return True
        # 用户问答响应
        if request.type == "question_response":
            if request.request_id in self._question_requests:
                answer: str | dict[Any, Any] = request.answer or ""
                # 尝试解析 JSON 格式的多选答案
                try:
                    parsed = json.loads(answer) if isinstance(answer, str) else answer
                    if isinstance(parsed, dict):
                        answer = parsed
                except (json.JSONDecodeError, TypeError):
                    pass
                self._question_requests[request.request_id].set_result(answer)
            await self._emit(BackendEvent(type="modal_request", modal=None))
            return True
        # 列出会话
        if request.type == "list_sessions":
            await self._handle_list_sessions()
            return True
        # 选择命令
        if request.type == "select_command":
            await self._handle_select_command(request.command or "")
            return True
        # 应用选择命令
        if request.type == "apply_select_command":
            if self._busy:
                await self._emit(BackendEvent(type="error", message="Session is busy"))
                return True
            self._busy = True
            try:
                self._active_line_task = asyncio.create_task(
                    self._apply_select_command(
                        request.command or "",
                        request.value or "",
                        request_id=getattr(request, "request_id", None),
                    )
                )
                should_continue = await self._active_line_task
            except asyncio.CancelledError:
                should_continue = True
            finally:
                self._active_line_task = None
                self._busy = False
                self._create_background_task(self._check_post_idle_bg())
            if not should_continue:
                await self._emit(BackendEvent(type="shutdown"))
                return False
            return True
        # btw 侧问
        if request.type == "btw_request":
            await self._handle_btw_request(request)
            return True
        if request.type == "btw_cancel":
            await self._handle_btw_cancel(request)
            return True
        # agent 向导
        if request.type == "agent_wizard_init":
            await self._handle_agent_wizard_init(request)
            return True
        if request.type == "agent_wizard_submit":
            await self._handle_agent_wizard_submit(request)
            return True
        if request.type == "agent_generate_request":
            await self._handle_agent_generate_request(request)
            return True
        # 未知请求类型
        if request.type != "submit_line":
            await self._emit(
                BackendEvent(type="error", message=f"Unknown request type: {request.type}")
            )
            return True
        # 忙碌中
        if self._busy:
            await self._emit(BackendEvent(type="error", message="Session is busy"))
            return True
        # 处理提交的行
        line = (request.line or "").strip()
        if not line:
            return True
        self._busy = True
        try:
            # treat_as_text=True 时跳过命令注册表，直接当 user 消息提交给 LLM
            # （前端非指定命令如 /resume、/model 走此路径，不被当作命令执行）
            if request.treat_as_text:
                self._active_line_task = asyncio.create_task(
                    self._submit_line_as_text(line)
                )
            else:
                self._active_line_task = asyncio.create_task(self._process_line(line))
            should_continue = await self._active_line_task
        except asyncio.CancelledError:
            should_continue = True
        finally:
            self._active_line_task = None
            self._busy = False
            self._create_background_task(self._check_post_idle_bg())
        if not should_continue:
            await self._emit(BackendEvent(type="shutdown"))
            return False
        return True

    async def _read_requests(self) -> None:
        """从 WebSocket 读取请求。"""
        while self._running:
            try:
                payload = await self._websocket.receive_text()
            except WebSocketDisconnect:
                self._ws_closed = True
                # 入队 shutdown 请求以唤醒主循环（可能正阻塞在 _request_queue.get()）
                await self._request_queue.put(FrontendRequest(type="shutdown"))
                await self._shutdown()
                return
            except (RuntimeError, OSError):
                self._ws_closed = True
                self._running = False
                log.warning("WebSocket read error, shutting down")
                await self._request_queue.put(FrontendRequest(type="shutdown"))
                return
            payload = payload.strip()
            if not payload:
                continue
            try:
                request = FrontendRequest.model_validate_json(payload)
                log.info("_read_requests: 解析请求 type=%s", request.type)
            except ValidationError as exc:  # 防御性协议处理
                log.warning("_read_requests: 请求解析失败: %s, payload=%s", exc, payload[:200])
                await self._emit(BackendEvent(type="error", message=f"Invalid request: {exc}"))
                continue

            # 立即解析模态对话框交互以避免死锁
            # 主循环在 _process_line() 中等待用户输入
            if request.type == "permission_response":
                if request.request_id in self._permission_requests:
                    self._permission_requests[request.request_id].set_result(bool(request.allowed))
                if request.always_allow and request.tool_name:
                    self._always_allowed_tools.add(request.tool_name)
                    if self._bundle is not None:
                        self._always_allowed_tools = add_always_allowed_tool(
                            self._bundle.cwd,
                            request.tool_name,
                        )
                await self._emit(BackendEvent(type="modal_request", modal=None))
                continue
            if request.type == "stop":
                await self._stop_active_line()
                continue
            if request.type == "question_response":
                if request.request_id in self._question_requests:
                    self._question_requests[request.request_id].set_result(request.answer or "")
                await self._emit(BackendEvent(type="modal_request", modal=None))
                continue

            await self._request_queue.put(request)

    async def _make_render_event(self) -> Callable[[StreamEvent], Awaitable[None]]:
        """创建共享的流式事件渲染器。

        返回一个 _render_event 闭包，供 _process_line 和 _submit_line_as_text 共用，
        消除重复代码并确保 TodoWrite/plan_mode_change 等事件处理一致。

        Returns:
            异步事件渲染函数
        """

        async def _render_event(event: StreamEvent) -> None:
            """渲染流式事件。"""
            # 助手文本增量
            if isinstance(event, AssistantTextDelta):
                reasoning = getattr(event, "reasoning", None)
                await self._emit(
                    BackendEvent(
                        type="assistant_delta",
                        message=event.text,
                        reasoning=reasoning if reasoning else None,
                    )
                )
                return
            # 助手回合完成
            if isinstance(event, AssistantTurnComplete):
                reasoning = event.message.thinking_text
                cleaned = _strip_tool_previews(event.message.text.strip(), event.message.tool_uses)
                await self._emit(
                    BackendEvent(
                        type="assistant_complete",
                        message=cleaned,
                        reasoning=reasoning if reasoning else None,
                        item=TranscriptItem(
                            role="assistant",
                            text=cleaned,
                            reasoning=reasoning if reasoning else None,
                        ),
                    )
                )
                await self._emit(BackendEvent.tasks_snapshot(get_task_manager().list_tasks()))
                # 透传最新累积用量与反推值到前端
                if self._bundle is not None:
                    sync_app_state(self._bundle)
                    # 更新会话 meta（CheckpointStore 已在 query_engine 内每轮 append）
                    from illusion.ui.runtime import _update_session_meta
                    _update_session_meta(self._bundle)
                return
            # 工具链开始
            if isinstance(event, ToolChainStarted):
                await self._update_phase("tool_executing")
                await self._emit(
                    BackendEvent(type="tool_chain_started", tool_count=event.tool_count)
                )
                return
            # 工具链完成
            if isinstance(event, ToolChainCompleted):
                await self._update_phase("thinking")
                await self._emit(BackendEvent(type="tool_chain_completed", phase="thinking"))
                return
            # 工具开始执行
            if isinstance(event, ToolExecutionStarted):
                tool_use_id = getattr(event, "tool_use_id", "") or ""
                if event.tool_input:
                    self._last_tool_inputs[event.tool_name] = event.tool_input
                if tool_use_id and tool_use_id in self._emitted_tool_started_ids:
                    if event.tool_input:
                        await self._emit(
                            BackendEvent(
                                type="tool_input_updated",
                                tool_name=event.tool_name,
                                tool_input=event.tool_input,
                                tool_use_id=tool_use_id,
                            )
                        )
                    return
                if tool_use_id:
                    self._emitted_tool_started_ids.add(tool_use_id)
                await self._emit(
                    BackendEvent(
                        type="tool_started",
                        tool_name=event.tool_name,
                        tool_input=event.tool_input,
                        item=TranscriptItem(
                            role="tool",
                            tool_name=event.tool_name,
                            tool_input=event.tool_input if event.tool_input else None,
                            tool_use_id=tool_use_id or None,
                            text=f"{event.tool_name} {json.dumps(event.tool_input, ensure_ascii=True)}"
                            if event.tool_input
                            else event.tool_name,
                        ),
                    )
                )
                return
            # 工具进度消息（对称于 backend_host，转发为 tool_progress 事件）
            if isinstance(event, ToolProgressEvent):
                await self._emit(
                    BackendEvent(
                        type="tool_progress",
                        tool_use_id=event.tool_use_id or None,
                        message=event.message,
                        progress_type=event.progress_type,
                    )
                )
                return
            # 工具执行完成
            if isinstance(event, ToolExecutionCompleted):
                tool_use_id = getattr(event, "tool_use_id", "") or ""
                await self._emit(
                    BackendEvent(
                        type="tool_completed",
                        tool_name=event.tool_name,
                        output=event.output,
                        is_error=event.is_error,
                        tool_use_id=tool_use_id or None,
                        item=TranscriptItem(
                            role="tool_result",
                            text=event.output,
                            tool_name=event.tool_name,
                            is_error=event.is_error,
                            tool_use_id=tool_use_id or None,
                        ),
                    )
                )
                # === Task/Todo 双向同步 ===
                # 仅 in_process_teammate 类型参与互通；同步后再发射快照保证前端看到一致状态
                _manager = get_task_manager()
                if event.tool_name in ("TodoWrite", "todo_write"):
                    tool_input = self._last_tool_inputs.get(event.tool_name, {})
                    todos = tool_input.get("todos") or []
                    if isinstance(todos, list):
                        todo_items = []
                        for item in todos:
                            if isinstance(item, dict):
                                todo_items.append(
                                    {
                                        "content": item.get("content", ""),
                                        "status": item.get("status", "pending"),
                                        "activeForm": item.get(
                                            "activeForm", item.get("content", "")
                                        ),
                                    }
                                )
                        if (
                            all(t.get("status") == "completed" for t in todo_items)
                            and len(todo_items) >= 1
                        ):
                            todo_items = []
                        await self._emit(BackendEvent(type="todo_update", todo_items=todo_items))
                await self._emit(BackendEvent.tasks_snapshot(_manager.list_tasks()))
                await self._emit(self._status_snapshot())
                # 计划相关工具完成时发送 plan_mode_change 事件
                if event.tool_name in (
                    "set_permission_mode",
                    "plan_mode",
                    "enter_plan_mode",
                    "exit_plan_mode",
                ):
                    assert self._bundle is not None
                    raw_mode = self._bundle.current_settings().permission.mode.value
                    formatted_mode = format_permission_mode(raw_mode)
                    self._bundle.app_state.set(permission_mode=raw_mode)
                    await self._emit(
                        BackendEvent(type="plan_mode_change", plan_mode=formatted_mode)
                    )
                    await self._emit(self._status_snapshot())
                return
            # 错误事件
            if isinstance(event, ErrorEvent):
                await self._emit(
                    BackendEvent(
                        type="transcript_item",
                        item=TranscriptItem(role="system", text=event.message),
                    )
                )
                return
            # 状态事件
            if isinstance(event, StatusEvent):
                if event.bg_agent:
                    await self._emit(BackendEvent(type="bg_agent_status", message=event.message))
                else:
                    await self._emit(
                        BackendEvent(
                            type="transcript_item",
                            item=TranscriptItem(role="system", text=event.message),
                        )
                    )
                return

        return _render_event

    async def _auto_resume_bg(self) -> None:
        """后台完成通知到达且主循环空闲时，自动进入 busy 处理通知。

        修复：idle 超时/用户退出 busy 后，通知只发前端 bg_agent_status 提示
        但无人消费，只能等手动输入。此方法由 on_task_complete 包装回调调度，
        自动恢复主循环处理积压通知。
        """
        if self._busy or self._bundle is None:
            return
        tracker = self._bundle.engine._bg_agent_tracker
        # 仅在有实际完成通知时才恢复处理，避免任务未完成时误触发 LLM 调用
        if tracker is None or not tracker.has_completions():
            return
        self._busy = True
        try:
            self._active_line_task = asyncio.create_task(self._process_bg_completions())
            await self._active_line_task
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("处理后台完成通知时出错")
            # 确保前端 busy 状态释放，避免异常路径卡死输入框
            await self._emit(BackendEvent(type="line_complete"))
        finally:
            self._active_line_task = None
            self._busy = False

    async def _process_bg_completions(self) -> bool:
        """处理积压的后台完成通知（自动进入 busy），不新增用户输入。"""
        assert self._bundle is not None
        # 清除上一轮的工具调用去重记录
        self._emitted_tool_started_ids.clear()
        # 更新会话阶段为思考中
        await self._update_phase("thinking")

        async def _print_system(message: str) -> None:
            """打印系统消息。"""
            await self._emit(
                BackendEvent(type="transcript_item", item=TranscriptItem(role="system", text=message))
            )

        # 复用共享的事件渲染器（含 TodoWrite/plan_mode_change 处理）
        _render_event = await self._make_render_event()

        should_continue = await handle_background_completions(
            self._bundle,
            print_system=_print_system,
            render_event=_render_event,
        )

        # 更新会话阶段为空闲
        await self._update_phase("idle")
        await self._emit(self._status_snapshot())
        await self._emit(BackendEvent.tasks_snapshot(get_task_manager().list_tasks()))
        await self._emit(BackendEvent(type="line_complete"))
        return should_continue

    async def _check_post_idle_bg(self) -> None:
        """_busy 变为 False 后检查是否有后台完成通知需要自动恢复。

        弥补斜杠命令执行期间后台完成通知被跳过的缺口：命令执行完后
        _busy=False，但后台在命令期间完成的通知未被消费，用此方法
        触发 _auto_resume_bg 恢复处理。
        """
        if self._bundle is not None:
            tracker = self._bundle.engine._bg_agent_tracker
            if tracker is not None and tracker.has_completions():
                self._create_background_task(self._auto_resume_bg())

    async def _process_line(self, line: str, *, transcript_line: str | None = None) -> bool:
        """处理用户输入的行内容。"""
        assert self._bundle is not None
        # 清除上一轮的工具调用去重记录
        self._emitted_tool_started_ids.clear()
        # 更新会话阶段为思考中
        await self._update_phase("thinking")
        # 发送用户消息（transcript_line 为 None 时不发送转录，用于左侧栏操作等静默场景）
        if transcript_line is not None:
            await self._emit(
                BackendEvent(
                    type="transcript_item",
                    item=TranscriptItem(role="user", text=transcript_line or line),
                )
            )

        async def _print_system(message: str) -> None:
            """打印系统消息。"""
            await self._emit(
                BackendEvent(
                    type="transcript_item", item=TranscriptItem(role="system", text=message)
                )
            )

        # 复用共享的事件渲染器（含 TodoWrite/plan_mode_change 处理）
        _render_event = await self._make_render_event()

        async def _replay_transcript_item(item: dict[str, Any]) -> None:
            """重播 transcript_item。"""
            await self._emit(BackendEvent(type="transcript_item", item=TranscriptItem(**item)))

        async def _clear_output() -> None:
            """清空输出。"""
            await self._emit(BackendEvent(type="clear_transcript"))

        async def _command_result_emitter(message: str, result_type: str) -> None:
            """发射指令结果事件。"""
            data: dict[str, Any] = {
                "message": message,
                "type": result_type,
            }
            # 回传当前请求的 ID（用于前端精确匹配响应）
            req_id = getattr(self, "_current_request_id", None)
            if req_id:
                data["request_id"] = req_id
                self._current_request_id = None  # 消费后清除，避免泄漏到后续事件
            await self._emit(
                BackendEvent(
                    type="command_result",
                    command_result_data=data,
                )
            )

        async def _replace_transcript_items(items: list[dict[str, Any]]) -> None:
            """替换转录项列表（一次性清空并替换，避免 Ink Static 重复渲染）。"""
            transcript_items = [TranscriptItem(**item) for item in items]
            await self._emit(BackendEvent(type="replace_transcript", items=transcript_items))

        should_continue = await handle_line(
            self._bundle,
            line,
            print_system=_print_system,
            render_event=_render_event,
            clear_output=_clear_output,
            replay_transcript_item=_replay_transcript_item,
            command_result_emitter=_command_result_emitter,
            replace_transcript_items=_replace_transcript_items,
        )

        # 更新会话阶段为空闲
        await self._update_phase("idle")
        await self._emit(self._status_snapshot())
        await self._emit(BackendEvent.tasks_snapshot(get_task_manager().list_tasks()))
        await self._emit(BackendEvent(type="line_complete"))
        return should_continue

    async def _submit_line_as_text(self, line: str) -> bool:
        """直接将用户输入当文本提交给 LLM，跳过命令注册表。

        用于前端 treat_as_text=True 的 submit_line 请求（非指定命令如
        /resume、/model 等），确保输入不被 commands.lookup 匹配为命令执行，
        而是作为普通 user 消息发给 LLM。

        Args:
            line: 用户输入的文本

        Returns:
            bool: 是否继续会话（始终返回 True）
        """
        assert self._bundle is not None
        self._emitted_tool_started_ids.clear()
        await self._update_phase("thinking")
        # 发送 user 消息到转录
        await self._emit(
            BackendEvent(type="transcript_item", item=TranscriptItem(role="user", text=line))
        )

        # 复用共享的事件渲染器（含 TodoWrite/plan_mode_change 处理）
        _render_event = await self._make_render_event()

        # 直接调用 engine.submit_message，跳过 handle_line 的命令注册表
        from illusion.engine.query import MaxTurnsExceeded

        settings = self._bundle.current_settings()
        self._bundle.engine.set_max_turns(settings.max_turns)
        from illusion.prompts import build_runtime_system_prompt

        system_prompt = build_runtime_system_prompt(
            settings,
            cwd=self._bundle.cwd,
            latest_user_prompt=line,
            channel_hint=self._bundle.channel_hint,
        )
        for ctx in self._bundle.hook_additional_contexts:
            if ctx:
                system_prompt = system_prompt + "\n\n" + _wrap_in_system_reminder(ctx)
        self._bundle.engine.set_system_prompt(system_prompt)
        try:
            async for event in self._bundle.engine.submit_message(line):
                await _render_event(event)
        except MaxTurnsExceeded as exc:
            await self._emit(
                BackendEvent(
                    type="transcript_item",
                    item=TranscriptItem(
                        role="system", text=f"Stopped after {exc.max_turns} turns (max_turns)."
                    ),
                )
            )
        # 更新会话 meta（替代旧 save_session_snapshot）
        from illusion.ui.runtime import _update_session_meta
        _update_session_meta(self._bundle)
        sync_app_state(self._bundle)
        await self._update_phase("idle")
        await self._emit(self._status_snapshot())
        await self._emit(BackendEvent.tasks_snapshot(get_task_manager().list_tasks()))
        await self._emit(BackendEvent(type="line_complete"))
        return True

    # rewind 两步选择的中间状态
    _rewind_target_idx: int | None = None

    async def _handle_rewind_message_selected(self, value: str) -> bool:
        """rewind 第一步：用户选择了要回退的消息，弹出模式选择。"""
        if self._bundle is None:
            return True
        try:
            target_idx = int(value)
        except ValueError:
            return True
        self._rewind_target_idx = target_idx
        state = self._bundle.app_state.get()
        zh = str(state.ui_language or "zh-CN").lower().startswith("zh")
        options = [
            {
                "value": "both",
                "label": "回退代码与对话" if zh else "Rewind code & conversation",
                "description": "撤销文件修改并移除对话"
                if zh
                else "Revert files and remove conversation",
            },
            {
                "value": "conversation",
                "label": "仅回退对话" if zh else "Rewind conversation only",
                "description": "只移除对话，保留文件修改"
                if zh
                else "Remove conversation, keep files",
            },
            {
                "value": "code",
                "label": "仅回退代码" if zh else "Rewind code only",
                "description": "只撤销文件修改，保留对话"
                if zh
                else "Revert files, keep conversation",
            },
        ]
        await self._emit(
            BackendEvent(
                type="select_request",
                modal={
                    "kind": "select",
                    "title": "回退方式" if zh else "Rewind mode",
                    "command": "rewind_mode",
                },
                select_options=options,
            )
        )
        return True

    async def _handle_rewind_mode_selected(self, value: str) -> bool:
        """rewind 第二步：用户选择了回退模式，执行回退。"""
        if self._bundle is None or self._rewind_target_idx is None:
            return True
        target_idx = self._rewind_target_idx
        self._rewind_target_idx = None
        mode = value.strip()
        if mode not in ("both", "conversation", "code"):
            return True
        messages = self._bundle.engine.messages
        # 计算 target 之后需回退的真实用户轮次（排除 / 命令与后台任务完成通知）
        turns = sum(
            1
            for i, msg in enumerate(messages)
            if i >= target_idx
            and msg.role == "user"
            and msg.text.strip()
            and not msg.text.strip().startswith("/")
            and not is_task_notification(msg.text)
        )
        if turns <= 0:
            return True
        return await self._process_line(f"/rewind {turns} {mode}", transcript_line="/rewind")

    async def _apply_select_command(self, command_name: str, value: str, request_id: str | None = None) -> bool:
        """应用选择的命令值。"""
        # 存储当前请求 ID，供 _command_result_emitter 回传
        self._current_request_id = request_id
        command = command_name.strip().lstrip("/").lower()
        selected = value.strip()
        # 特殊路由：context → change window 时弹出子选择器
        if command == "context" and selected == "__change_window__":
            await self._handle_select_command("context-window")
            return True
        # context-window → __custom__ 由前端 CustomInputModal 接管，此处不应到达
        # 防御性处理：静默忽略并提示前端关闭选择框
        if command == "context-window" and selected == "__custom__":
            await self._emit(BackendEvent(type="line_complete"))
            return True
        # rewind 两步选择：第一步（选消息）→ 存储目标，弹出模式选择
        if command == "rewind":
            return await self._handle_rewind_message_selected(selected)
        # rewind 两步选择：第二步（选模式）→ 执行回退
        if command == "rewind_mode":
            return await self._handle_rewind_mode_selected(selected)
        # resume 命令：独立处理，不通过 _process_line，避免触发输入框命令交互
        if command == "resume":
            return await self._restore_session(selected)
        line = self._build_select_command_line(command, selected)
        if line is None:
            await self._emit(
                BackendEvent(type="error", message=f"Unknown select command: {command_name}")
            )
            await self._emit(BackendEvent(type="line_complete"))
            return True
        return await self._process_line(line, transcript_line=f"/{command}")

    async def _restore_session(self, session_id: str) -> bool:
        """恢复会话（独立处理，不触发输入框命令交互）。

        这个函数直接调用 resume_handler，不通过 _process_line，
        避免发送 transcript_item 事件显示用户输入的命令。
        """
        assert self._bundle is not None
        from illusion.commands.session import resume_handler
        from illusion.commands.types import CommandContext

        # 创建命令上下文
        context = CommandContext(
            engine=self._bundle.engine,
            hooks_summary=self._bundle.hook_summary(),
            mcp_summary=self._bundle.mcp_summary(),
            plugin_summary=self._bundle.plugin_summary(),
            cwd=self._bundle.cwd,
            tool_registry=self._bundle.tool_registry,
            app_state=self._bundle.app_state,
            session_id=self._bundle.session_id,
        )

        # 调用 resume_handler 恢复会话
        result = await resume_handler(session_id, context)

        # 处理恢复结果
        if result.restored_session_id:
            self._bundle.session_id = result.restored_session_id

        # 会话指令后刷新状态
        if result.refresh_state:
            sync_app_state(self._bundle)

        # 如果有 replay_messages，替换转录项（复用共享的 build_replay_items 函数）
        if result.replay_messages:
            from illusion.ui.web.ws_web_api import build_replay_items

            replay_items = build_replay_items(result.replay_messages)
            transcript_items = [TranscriptItem(**item) for item in replay_items]
            await self._emit(BackendEvent(type="replace_transcript", items=transcript_items))

        # 发送状态更新
        await self._emit(self._status_snapshot())
        await self._emit(BackendEvent.tasks_snapshot(get_task_manager().list_tasks()))
        await self._emit(BackendEvent(type="line_complete"))
        return True

    def _build_select_command_line(self, command: str, value: str) -> str | None:
        """构建选择命令的实际命令字符串。"""
        if command == "env":
            return f"/env {value}"
        if command == "resume":
            return f"/resume {value}" if value else "/resume"
        if command == "permissions":
            return f"/permissions {value}"
        if command == "language":
            return f"/language {value}"
        if command == "output-style":
            return f"/output-style {value}"
        if command == "effort":
            return f"/effort {value}"
        if command == "max-tokens":
            # custom 由前端转为数字字符串，直接透传
            return f"/max-tokens {value}"
        if command == "turns":
            return f"/turns {value}"
        if command == "agent":
            return f"/agent {value}"
        if command == "model":
            return f"/model set {value}"
        if command == "delete":
            if value == "__all__":
                return "/delete all"
            return f"/delete {value}"
        if command == "rules":
            return f"/rules {value}"
        if command == "skills":
            return f"/skills {value}"
        if command == "context":
            if value == "__usage__":
                return "/context __usage__"
            return None
        if command == "context-window":
            return f"/context set {value}"
        return None

    def _status_snapshot(self) -> BackendEvent:
        """生成状态快照事件。"""
        assert self._bundle is not None
        return BackendEvent.status_snapshot(
            state=self._bundle.app_state.get(),
            mcp_servers=self._bundle.mcp_manager.list_statuses(),
        )

    def _emit_swarm_status(
        self, teammates: list[dict[str, Any]], notifications: list[dict[str, Any]] | None = None
    ) -> None:
        """同步发送 swarm_status 事件（调度为协程）。"""
        self._create_background_task(
            self._emit(
                BackendEvent(
                    type="swarm_status",
                    swarm_teammates=teammates,
                    swarm_notifications=notifications,
                )
            )
        )

    async def _handle_list_sessions(self) -> None:
        """处理列出会话请求。"""
        import time as _time

        from illusion.services.session_storage import list_session_snapshots

        assert self._bundle is not None
        locale = str(
            self._bundle.app_state.get().ui_language or self._bundle.current_settings().ui_language
        )
        zh = locale.lower().startswith("zh")
        sessions = list_session_snapshots(self._bundle.cwd, limit=10)
        options = []
        for s in sessions:
            ts = _time.strftime("%m/%d %H:%M", _time.localtime(s["created_at"]))
            summary = s.get("summary", "")[:50] or ("（无摘要）" if zh else "(no summary)")
            options.append(
                {
                    "value": s["session_id"],
                    "label": f"{ts}  {s['message_count']}msg  {summary}",
                }
            )
        await self._emit(
            BackendEvent(
                type="select_request",
                modal={
                    "kind": "select",
                    "title": "恢复会话" if zh else "Resume Session",
                    "command": "resume",
                },
                select_options=options,
            )
        )

    async def _handle_select_command(self, command_name: str) -> None:
        """处理选择命令请求。"""
        assert self._bundle is not None
        command = command_name.strip().lstrip("/").lower()
        if command == "resume":
            await self._handle_list_sessions()
            return

        settings = self._bundle.current_settings()
        state = self._bundle.app_state.get()
        locale = str(state.ui_language or settings.ui_language)
        zh = locale.lower().startswith("zh")
        current_model = settings.active_model_name

        if command == "env":
            statuses = AuthManager(settings).get_env_credential_statuses()
            options = [
                {
                    "value": env_key,
                    "label": f"{env_key} ({info['api_format']})",
                    "description": f"{info['api_format']} / {info['model']}"
                    + (" [active]" if info["active"] else ""),
                    "active": info["active"],
                }
                for env_key, info in statuses.items()
            ]
            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={
                        "kind": "select",
                        "title": "环境配置" if zh else "Env Config",
                        "command": "env",
                    },
                    select_options=options,
                )
            )
            return

        if command == "permissions":
            options = [
                {
                    "value": "default",
                    "label": "默认" if zh else "Default",
                    "description": "写入/执行前询问"
                    if zh
                    else "Ask before write/execute operations",
                    "active": settings.permission.mode.value == "default",
                },
                {
                    "value": "full_auto",
                    "label": "自动" if zh else "Auto",
                    "description": "自动允许所有工具" if zh else "Allow all tools automatically",
                    "active": settings.permission.mode.value == "full_auto",
                },
                {
                    "value": "plan",
                    "label": "计划模式" if zh else "Plan Mode",
                    "description": "阻止所有写入操作" if zh else "Block all write operations",
                    "active": settings.permission.mode.value == "plan",
                },
            ]
            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={
                        "kind": "select",
                        "title": "权限模式" if zh else "Permission Mode",
                        "command": "permissions",
                    },
                    select_options=options,
                )
            )
            return

        if command == "output-style":
            options = [
                {
                    "value": style.name,
                    "label": style.name,
                    "description": style.source,
                    "active": style.name == settings.output_style,
                }
                for style in load_output_styles()
            ]
            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={
                        "kind": "select",
                        "title": "输出风格" if zh else "Output Style",
                        "command": "output-style",
                    },
                    select_options=options,
                )
            )
            return

        if command == "effort":
            options = [
                {
                    "value": "low",
                    "label": "低" if zh else "Low",
                    "description": "最快响应" if zh else "Fastest responses",
                    "active": settings.effort == "low",
                },
                {
                    "value": "medium",
                    "label": "中" if zh else "Medium",
                    "description": "平衡推理" if zh else "Balanced reasoning",
                    "active": settings.effort == "medium",
                },
                {
                    "value": "high",
                    "label": "高" if zh else "High",
                    "description": "最深推理" if zh else "Deepest reasoning",
                    "active": settings.effort == "high",
                },
                {
                    "value": "xhigh",
                    "label": "超高" if zh else "XHigh",
                    "description": "超深推理" if zh else "Extra deep reasoning",
                    "active": settings.effort == "xhigh",
                },
                {
                    "value": "max",
                    "label": "最大" if zh else "Max",
                    "description": "最大推理深度" if zh else "Maximum reasoning depth",
                    "active": settings.effort == "max",
                },
            ]
            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={
                        "kind": "select",
                        "title": "推理强度" if zh else "Reasoning Effort",
                        "command": "effort",
                    },
                    select_options=options,
                )
            )
            return

        if command == "max-tokens":
            current = int(state.max_tokens or settings.max_tokens)
            presets = [
                ("8k", 8192),
                ("16k", 16384),
                ("32k", 32768),
                ("64k", 65536),
                ("128k", 131072),
            ]
            options = [
                {
                    "value": key,
                    "label": key.upper(),
                    "description": f"{tokens} tokens",
                    "active": tokens == current,
                }
                for key, tokens in presets
            ]
            # 自定义档位
            options.append({
                "value": "custom",
                "label": "自定义" if zh else "Custom",
                "description": "手动输入数字" if zh else "Enter custom number",
                "active": current not in {tokens for _, tokens in presets},
            })
            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={
                        "kind": "select",
                        "title": "最大令牌数" if zh else "Max Tokens",
                        "command": "max-tokens",
                    },
                    select_options=options,
                )
            )
            return

        if command == "turns":
            current_turns: int | None = self._bundle.engine.max_turns
            values = {32, 64, 128, 200, 256, 512}
            if isinstance(current_turns, int):
                values.add(current_turns)
            options = [
                {
                    "value": "unlimited",
                    "label": "无限" if zh else "Unlimited",
                    "description": "不对本会话硬性停止" if zh else "Do not hard-stop this session",
                    "active": current_turns is None,
                }
            ]
            options.extend(
                {
                    "value": str(value),
                    "label": (f"{value} 轮" if zh else f"{value} turns"),
                    "active": value == current_turns,
                }
                for value in sorted(values)
            )
            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={
                        "kind": "select",
                        "title": "最大轮数" if zh else "Max Turns",
                        "command": "turns",
                    },
                    select_options=options,
                )
            )
            return

        if command == "agent":
            # 列出已完成 agent 任务摘要（前台 tool_result + 后台 task-notification）
            from illusion.config.paths import get_tasks_dir
            from illusion.engine.messages import TextBlock, ToolResultBlock
            from illusion.tasks.types import TASK_NOTIFICATION_RE

            task_options: list[dict[str, Any]] = []
            order = 0

            # 1. 前台 agent：从 transcript 提取 tool_result（跳过后台启动通知）
            pending_labels: dict[str, str] = {}
            for msg in self._bundle.engine.messages:
                if msg.role == "assistant":
                    for use_block in msg.tool_uses:
                        if use_block.name == "agent":
                            inp = use_block.input or {}
                            task_name = str(inp.get("description") or inp.get("name") or "agent")[:30]
                            subagent_type = inp.get("subagent_type")
                            if subagent_type:
                                agent_type = "".join(
                                    w.title() for w in str(subagent_type).replace("_", "-").split("-")
                                )
                            elif inp:
                                agent_type = "GeneralPurpose"
                            else:
                                agent_type = "Agent"
                            pending_labels[use_block.id] = f"{task_name} · {agent_type}"
                elif msg.role == "user":
                    for result_block in msg.content:
                        if isinstance(result_block, ToolResultBlock) and result_block.tool_use_id in pending_labels:
                            text = result_block.text_content
                            if text and ("launched in background" in text or "launched as subprocess" in text):
                                continue
                            order += 1
                            first_line = text.split("\n", 1)[0][:60] if text else ("（无摘要）" if zh else "(no summary)")
                            task_options.append({
                                "value": result_block.tool_use_id,
                                "label": f"#{order} {pending_labels[result_block.tool_use_id]}",
                                "description": first_line,
                            })

            # 2. 后台任务：从 transcript 的 task-notification 提取
            tasks_dir = get_tasks_dir()
            for msg in self._bundle.engine.messages:
                if msg.role != "user":
                    continue
                for text_block in msg.content:
                    if not isinstance(text_block, TextBlock):
                        continue
                    match = TASK_NOTIFICATION_RE.search(text_block.text)
                    if not match:
                        continue
                    if match.group("status").strip() != "completed":
                        continue
                    task_id = match.group("task_id").strip()
                    task_name = (match.group("task_name") or "").strip()
                    summary_tag = match.group("summary").strip()
                    result_text = match.group("result").strip()
                    if not result_text:
                        try:
                            log_file = tasks_dir / f"{task_id}.log"
                            if log_file.exists():
                                content = log_file.read_text(encoding="utf-8", errors="replace")
                                result_text = content[-12000:] if len(content) > 12000 else content
                        except OSError:
                            pass
                    order += 1
                    if task_name:
                        label_name = task_name
                    else:
                        name_match = re.match(r"Agent '([^']+)'", summary_tag)
                        label_name = name_match.group(1) if name_match else (summary_tag or "agent")
                    first_line = result_text.split("\n", 1)[0][:60] if result_text else ("（无摘要）" if zh else "(no summary)")
                    task_options.append({
                        "value": task_id,
                        "label": f"#{order} {label_name}",
                        "description": first_line,
                    })

            if not task_options:
                await self._emit(BackendEvent(type="error", message=("没有已完成的 agent" if zh else "No completed agents")))
                return
            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={"kind": "select", "title": ("已完成任务摘要" if zh else "Completed Task Summary"), "command": "agent"},
                    select_options=task_options,
                )
            )
            return

        if command == "language":
            current_lang = str(state.ui_language or "zh-CN")
            options = [
                {
                    "value": "set zh-CN",
                    "label": "简体中文",
                    "description": "中文界面",
                    "active": current_lang == "zh-CN",
                },
                {
                    "value": "set en",
                    "label": "English",
                    "description": "English UI",
                    "active": current_lang == "en",
                },
            ]
            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={
                        "kind": "select",
                        "title": "语言" if zh else "Language",
                        "command": "language",
                    },
                    select_options=options,
                )
            )
            return

        if command == "model":
            options = self._model_select_options(current_model)
            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={
                        "kind": "select",
                        "title": "模型" if zh else "Model",
                        "command": "model",
                    },
                    select_options=options,
                )
            )
            return

        if command == "rewind":
            messages = self._bundle.engine.messages
            # 过滤后台任务完成通知（<task-notification>），它们不应出现在回退选项中
            user_msgs = [
                (i, msg)
                for i, msg in enumerate(messages)
                if msg.role == "user" and msg.text.strip()
                and not msg.text.strip().startswith("/")
                and not is_task_notification(msg.text)
            ]
            if not user_msgs:
                await self._emit(
                    BackendEvent(
                        type="error",
                        message=("没有可回退的消息。" if zh else "No messages to rewind to."),
                    )
                )
                return
            options = []
            total = len(user_msgs)
            for k, (idx, msg) in enumerate(reversed(user_msgs)):
                text = msg.text.strip()
                label = text[:80] + ("…" if len(text) > 80 else "")
                options.append(
                    {
                        "value": str(idx),
                        "label": label,
                        "description": f"#{total - k}",
                    }
                )
            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={
                        "kind": "select",
                        "title": "回退到" if zh else "Rewind to",
                        "command": "rewind",
                    },
                    select_options=options,
                )
            )
            return

        if command == "delete":
            import time as _time

            from illusion.services.session_storage import list_session_snapshots

            sessions = list_session_snapshots(self._bundle.cwd, limit=10)
            if not sessions:
                await self._emit(
                    BackendEvent(
                        type="error",
                        message=("没有已保存的会话。" if zh else "No saved sessions found."),
                    )
                )
                return
            options = []
            for s in sessions:
                ts = _time.strftime("%m/%d %H:%M", _time.localtime(s["created_at"]))
                summary = s.get("summary", "")[:50] or ("（无摘要）" if zh else "(no summary)")
                options.append(
                    {
                        "value": s["session_id"],
                        "label": f"{ts}  {s['message_count']}msg  {summary}",
                    }
                )
            options.append(
                {
                    "value": "__all__",
                    "label": ("清除所有会话" if zh else "Delete all sessions"),
                    "description": (
                        "删除全部已保存的会话快照" if zh else "Remove all saved session snapshots"
                    ),
                }
            )
            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={
                        "kind": "select",
                        "title": "删除会话" if zh else "Delete Session",
                        "command": "delete",
                    },
                    select_options=options,
                )
            )
            return

        if command == "rules":
            # 加载项目级权限配置
            from illusion.permissions.loader import (
                filter_rules_by_permissions,
                is_rules_disabled,
                load_project_permissions,
            )
            from illusion.skills.loader import get_project_rules_dir

            project_permissions = load_project_permissions(self._bundle.cwd)

            # 检查是否禁用所有 rules
            if is_rules_disabled(project_permissions):
                await self._emit(
                    BackendEvent(
                        type="error",
                        message=("所有规则已被禁用" if zh else "All rules are disabled"),
                    )
                )
                return

            rules_dir = get_project_rules_dir(self._bundle.cwd)
            all_rule_files = sorted(rules_dir.glob("*.md"))
            if not all_rule_files:
                await self._emit(
                    BackendEvent(
                        type="error",
                        message=(
                            f"没有找到规则文件：{rules_dir}"
                            if zh
                            else f"No rules found in {rules_dir}"
                        ),
                    )
                )
                return

            # 过滤掉被禁用的 rules
            rule_files = filter_rules_by_permissions(all_rule_files, project_permissions)

            options = []
            for path in rule_files:
                content = path.read_text(encoding="utf-8", errors="replace").strip()
                first_line = (
                    content.split("\n", 1)[0][:60] if content else ("（空）" if zh else "(empty)")
                )
                options.append(
                    {
                        "value": path.stem,
                        "label": path.stem,
                        "description": first_line,
                    }
                )
            if not options:
                await self._emit(
                    BackendEvent(
                        type="error",
                        message=("没有可用的规则文件" if zh else "No available rules files"),
                    )
                )
                return
            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={
                        "kind": "select",
                        "title": "查看规则" if zh else "View Rules",
                        "command": "rules",
                    },
                    select_options=options,
                )
            )
            return

        if command == "skills":
            from illusion.skills.loader import load_skill_registry

            skill_registry = load_skill_registry(self._bundle.cwd)
            skills = skill_registry.list_skills()

            if not skills:
                await self._emit(BackendEvent(type="error", message="No skills available."))
                return

            options = []
            for skill in skills:
                source = f" [{skill.source}]"
                first_line = (
                    skill.description.split("\n", 1)[0][:60]
                    if skill.description
                    else ("（空）" if zh else "(empty)")
                )
                options.append(
                    {
                        "value": skill.name,
                        "label": f"{skill.name}{source}",
                        "description": first_line,
                    }
                )

            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={
                        "kind": "select",
                        "title": "查看技能" if zh else "View Skills",
                        "command": "skills",
                    },
                    select_options=options,
                )
            )
            return

        if command == "context":
            current_window = settings.context_window
            # 上下文占用：最后一次 API 调用的真实值 + 新增消息估算
            estimated = self._bundle.engine.current_context_tokens()
            percentage = round(estimated * 100 / current_window) if current_window > 0 else 0
            options = [
                {
                    "value": "__change_window__",
                    "label": "修改上下文窗口大小" if zh else "Change context window size",
                    "description": f"当前: {current_window:,} tokens"
                    if zh
                    else f"Current: {current_window:,} tokens",
                },
                {
                    "value": "__usage__",
                    "label": "查看上下文使用情况" if zh else "View context usage",
                    "description": f"已用: ~{estimated:,} / {current_window:,} tokens ({percentage}%)"
                    if zh
                    else f"Used: ~{estimated:,} / {current_window:,} tokens ({percentage}%)",
                },
            ]
            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={
                        "kind": "select",
                        "title": "上下文管理" if zh else "Context Management",
                        "command": "context",
                    },
                    select_options=options,
                )
            )
            return

        if command == "context-window":
            current = settings.context_window
            preset_values = [128_000, 200_000, 512_000, 1_000_000]
            if current not in preset_values:
                preset_values.append(current)
            preset_values.sort()
            options = [
                {
                    "value": str(v),
                    "label": f"{v:,} tokens",
                    "active": v == current,
                }
                for v in preset_values
            ]
            options.append(
                {
                    "value": "__custom__",
                    "label": "其他（自定义输入）" if zh else "Other (custom)",
                }
            )
            await self._emit(
                BackendEvent(
                    type="select_request",
                    modal={
                        "kind": "select",
                        "title": "上下文窗口大小" if zh else "Context Window Size",
                        "command": "context-window",
                    },
                    select_options=options,
                )
            )
            return

        await self._emit(
            BackendEvent(
                type="error",
                message=(
                    f"/{command} 暂无可选项" if zh else f"No selector available for /{command}"
                ),
            )
        )

    def _model_select_options(self, current_model: str) -> list[dict[str, object]]:
        """从 settings.json 的 env_N 配置中提取所有实际可用的模型。"""
        assert self._bundle is not None
        settings = self._bundle.current_settings()
        envs = settings.list_envs()

        seen: set[str] = set()
        options: list[dict[str, object]] = []

        # 当前模型排第一位（value 用 model 引用，label 用显示名）
        if settings.model:
            seen.add(settings.model)
            options.append(
                {
                    "value": settings.model,
                    "label": current_model,
                    "description": "Current",
                    "active": True,
                }
            )

        # 遍历所有 env，提取 model_N
        for env_key, env in envs.items():
            for model_key, model_name in env.list_models().items():
                ref = f"{env_key}.{model_key}"
                if ref in seen:
                    continue
                seen.add(ref)
                is_current = ref == settings.model
                options.append(
                    {
                        "value": ref,
                        "label": model_name,
                        "description": f"{env_key} ({env.api_format})",
                        "active": is_current,
                    }
                )

        return options

    async def _ask_permission(self, tool_name: str, reason: str) -> bool:
        """请求用户权限确认。

        如果工具在"总是允许"列表中，则直接允许。
        否则通过 WebSocket 发送权限请求模态框，等待用户响应。

        Args:
            tool_name: 工具名称
            reason: 权限请求原因

        Returns:
            bool: 用户是否允许
        """
        # 如果工具在"总是允许"列表中，则直接允许
        if tool_name in self._always_allowed_tools:
            return True
        # 串行化 modal 请求：前端 modal 是单例，并发请求会互相覆盖
        async with self._modal_lock:
            request_id = uuid4().hex
            future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
            self._permission_requests[request_id] = future
            await self._emit(
                BackendEvent(
                    type="modal_request",
                    modal={
                        "kind": "permission",
                        "request_id": request_id,
                        "tool_name": tool_name,
                        "reason": reason,
                    },
                )
            )
            try:
                return await future
            finally:
                self._permission_requests.pop(request_id, None)

    async def _ask_question(self, question: str, questions: object = None) -> str | dict[Any, Any]:
        """向用户提问并等待回答。

        Args:
            question: 提问内容
            questions: 结构化问题数据（可选）

        Returns:
            str | dict[str, Any]: 用户回答
        """
        # 串行化 modal 请求：前端 modal 是单例，并发请求会互相覆盖
        async with self._modal_lock:
            request_id = uuid4().hex
            future: asyncio.Future[str | dict[Any, Any]] = asyncio.get_running_loop().create_future()
            self._question_requests[request_id] = future
            # 优先使用显式传入的结构化问题数据，回退到 _last_tool_inputs
            questions_data = questions
            if questions_data is None:
                tool_input = self._last_tool_inputs.get("ask_user_question", {})
                questions_data = tool_input.get("questions")
            # 如果是 pydantic 模型列表，转为 dict[str, Any]
            if questions_data is not None and isinstance(questions_data, list):
                questions_data = [
                    q.model_dump() if hasattr(q, "model_dump") else q for q in questions_data
                ]
            modal_payload: dict[str, Any] = {
                "kind": "question",
                "request_id": request_id,
                "question": question,
            }
            if questions_data:
                modal_payload["questions"] = questions_data
            await self._emit(
                BackendEvent(
                    type="modal_request",
                    modal=modal_payload,
                )
            )
            try:
                return await future
            finally:
                self._question_requests.pop(request_id, None)

    async def _ask_plan_approval(self, plan: str) -> tuple[bool, str]:
        """向用户展示计划并等待审批。

        先将计划内容作为 plan 消息写入对话流，再复用 question 模态让用户选择批准或拒绝。
        用户可通过"其他"选项输入反馈文字。

        Args:
            plan: 计划内容（Markdown 格式）

        Returns:
            tuple[bool, str]: (是否批准, 用户反馈)
        """
        # 将计划写入对话流
        await self._emit(
            BackendEvent(
                type="transcript_item",
                item=TranscriptItem(role="plan", text=plan),
            )
        )
        # 复用 question 模态，提供批准/拒绝选项
        from illusion.config.i18n import t as _t

        # 串行化 modal 请求：前端 modal 是单例，并发请求会互相覆盖
        async with self._modal_lock:
            request_id = uuid4().hex
            future: asyncio.Future[str | dict[Any, Any]] = asyncio.get_running_loop().create_future()
            self._question_requests[request_id] = future
            approve_label = _t("plan_approve")
            reject_label = _t("plan_reject")
            modal_payload: dict[str, Any] = {
                "kind": "question",
                "request_id": request_id,
                "question": _t("plan_approval"),
                "plan": plan,
                "questions": [
                    {
                        "question": _t("plan_approve_question"),
                        "header": "approval",
                        "options": [
                            {"label": approve_label, "description": _t("plan_start_impl")},
                            {"label": reject_label, "description": _t("plan_return_mode")},
                        ],
                        "multiSelect": False,
                    }
                ],
            }
            await self._emit(
                BackendEvent(
                    type="modal_request",
                    modal=modal_payload,
                )
            )
            try:
                answer = await future
                # 解析用户回答
                answer = str(answer).strip()
                if answer == f"1. {approve_label}" or answer == approve_label:
                    return True, ""
                elif answer == f"2. {reject_label}" or answer == reject_label:
                    return False, ""
                else:
                    # 用户通过"其他"输入的反馈文字
                    return False, answer
            finally:
                self._question_requests.pop(request_id, None)

    async def _stop_active_line(self) -> None:
        """停止当前活动的行处理任务。"""
        task = self._active_line_task
        # 检查是否有运行中的后台任务：主循环空闲（后台 agent 在跑）时
        # _active_line_task 为 None，但 stop 仍应终止 agent 进程
        has_running_tasks = False
        if self._bundle is not None:
            has_running_tasks = any(
                t.status in ("running", "pending")
                for t in get_task_manager().list_tasks()
            )
        if (task is None or task.done()) and not has_running_tasks:
            from illusion.config.i18n import t as _t

            await self._emit(
                BackendEvent(
                    type="command_result",
                    command_result_data={"message": _t("no_active_task"), "type": "info"},
                )
            )
            return
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("停止行处理任务异常")
        # 停止所有正在运行的后台任务（agent / bash / powershell 等）
        if self._bundle is not None:
            from illusion.ui.runtime import stop_all_tasks
            await stop_all_tasks(self._bundle)
        self._busy = False
        await self._update_phase("idle")
        await self._emit(BackendEvent(type="modal_request", modal=None))
        from illusion.config.i18n import t as _t

        stopped_message = _t("task_stopped")
        await self._emit(
            BackendEvent(
                type="transcript_item",
                item=TranscriptItem(role="system", text=stopped_message),
            )
        )
        await self._emit(
            BackendEvent(
                type="command_result",
                command_result_data={"message": stopped_message, "type": "info"},
            )
        )
        await self._emit(self._status_snapshot())
        await self._emit(BackendEvent.tasks_snapshot(get_task_manager().list_tasks()))
        await self._emit(BackendEvent(type="line_complete"))

    async def _update_phase(self, phase: str) -> None:
        """更新会话阶段。

        Args:
            phase: 新的会话阶段（idle/thinking/tool_executing）
        """
        assert self._bundle is not None
        self._bundle.app_state.set(phase=phase)

    async def _write_loop(self) -> None:
        """单一消费者：串行化所有 WebSocket 写入。

        所有 _emit() 调用通过 _write_queue，确保 FIFO 排序和无并发 WebSocket 写入。
        收到 QueueShutDown 后退出循环；写入异常时只记录日志，不退出（与原版
        asyncio.Lock 实现一致），避免瞬态错误导致写循环永久退出、后续所有事件
        （如 modal_request modal=None、task_stopped、line_complete）丢失，
        进而引发权限模态框不消失、Ctrl+X 看似无效等连锁问题。
        """
        while True:
            try:
                event = await self._write_queue.get()
            except QueueShutDown:
                break
            try:
                payload = event.model_dump_json()
                await self._websocket.send_text(payload)
            except (WebSocketDisconnect, RuntimeError, OSError, ValueError, TypeError):
                # 不 break：瞬态写入失败不应终止写循环，否则后续事件全部丢失。
                # 真正的连接断开由 _read_requests 的 WebSocketDisconnect 处理，
                # 它会入队 shutdown 请求并调用 _shutdown 关闭队列。
                log.debug("WebSocket 写入失败，跳过本次发送")

    async def _emit(self, event: BackendEvent) -> None:
        """入队事件给写循环。非阻塞。

        Args:
            event: 要发送的后端事件
        """
        try:
            self._write_queue.put_nowait(event)
        except QueueShutDown:
            pass  # 正在关闭，丢弃事件

    async def _handle_btw_request(self, req: FrontendRequest) -> None:
        """处理 btw_request：发起侧问并返回 btw_response。

        将 side_question 调用包装为后台任务，存入 _btw_tasks 以支持
        btw_cancel 中途取消。任务完成后（无论成功/失败）自动从映射移除。
        """
        assert self._bundle is not None
        request_id = req.request_id or ""
        engine = self._bundle.engine
        question = req.question or ""

        async def _run() -> None:
            try:
                reply = await run_side_question(question, engine)
                await self._emit(
                    BackendEvent(type="btw_response", request_id=request_id, reply=reply)
                )
            except SideQuestionError as exc:
                await self._emit(
                    BackendEvent(type="btw_response", request_id=request_id, error=str(exc))
                )
            except Exception as exc:  # noqa: BLE001
                await self._emit(
                    BackendEvent(type="btw_response", request_id=request_id, error=str(exc))
                )
            finally:
                self._btw_tasks.pop(request_id, None)

        task = self._create_background_task(_run())
        self._btw_tasks[request_id] = task

    async def _handle_btw_cancel(self, req: FrontendRequest) -> None:
        """处理 btw_cancel：取消进行中的侧问任务并回复 cancelled。"""
        request_id = req.request_id or ""
        task = self._btw_tasks.pop(request_id, None)
        if task is not None:
            task.cancel()
        await self._emit(
            BackendEvent(type="btw_response", request_id=request_id, error="cancelled")
        )

    async def _handle_agent_wizard_init(self, req: FrontendRequest) -> None:
        """处理 agent_wizard_init：返回可用工具/模型列表。"""
        assert self._bundle is not None
        tools = list_available_tools(self._bundle.tool_registry)
        models = list_available_models(self._bundle.app_state)
        await self._emit(BackendEvent(type="agent_wizard_init_response", tools=tools, models=models))

    async def _handle_agent_wizard_submit(self, req: FrontendRequest) -> None:
        """处理 agent_wizard_submit：校验并写入 agent 定义文件。"""
        assert self._bundle is not None
        fields = req.fields or {}
        scope = req.scope or "user"
        errors = validate_agent_definition(fields, self._bundle.cwd)
        if errors:
            await self._emit(BackendEvent(type="agent_wizard_result", success=False, errors=errors))
            return
        try:
            path = write_agent_definition(fields, scope, self._bundle.cwd)
        except OSError as exc:
            await self._emit(BackendEvent(type="agent_wizard_result", success=False, errors={"_": str(exc)}))
            return
        await self._emit(BackendEvent(type="agent_wizard_result", success=True, path=str(path)))

    async def _handle_agent_generate_request(self, req: FrontendRequest) -> None:
        """处理 agent_generate_request：LLM 辅助生成 agent 配置。"""
        assert self._bundle is not None
        request_id = req.request_id or ""
        engine = self._bundle.engine
        existing = [a.name for a in get_all_agent_definitions()]
        try:
            generated = await generate_agent_from_description(
                req.prompt or "", req.model or "inherit", existing, engine,
            )
            await self._emit(BackendEvent(
                type="agent_generate_response",
                request_id=request_id,
                agent={"identifier": generated.identifier, "when_to_use": generated.when_to_use, "system_prompt": generated.system_prompt},
            ))
        except Exception as exc:  # noqa: BLE001
            await self._emit(BackendEvent(
                type="agent_generate_response",
                request_id=request_id,
                error=str(exc),
            ))

    def _create_background_task(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        """创建 fire-and-forget task 并保留强引用，防止 GC 回收未完成 task。

        Args:
            coro: 要执行的协程

        Returns:
            asyncio.Task: 创建的 task，完成后自动从 _dispatch_tasks 移除
        """
        task = asyncio.create_task(coro)
        self._dispatch_tasks.add(task)
        task.add_done_callback(self._dispatch_tasks.discard)
        return task

    def _resolve_pending_futures(self) -> None:
        """resolve 所有 pending permission/question futures，防止永久阻塞。"""
        for fut in self._permission_requests.values():
            if not fut.done():
                fut.set_result(False)  # 默认拒绝
        self._permission_requests.clear()

        for quest_fut in self._question_requests.values():
            if not quest_fut.done():
                quest_fut.set_result("")  # 默认空答
        self._question_requests.clear()

    async def _shutdown(self) -> None:
        """优雅关闭，按严格顺序释放资源。

        不包含 stderr 卸载、SIGINT 移除、stdin 线程停止、runtime 关闭
        （runtime 由 run() finally 块关闭）。
        """
        # 1. resolve 所有 pending permission/question futures
        self._resolve_pending_futures()

        # 2. 取消周期状态更新 task
        if self._periodic_task is not None and not self._periodic_task.done():
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("周期状态更新 task 关闭异常")

        # 3. gather 所有 dispatch tasks（return_exceptions=True 不抛异常）
        if self._dispatch_tasks:
            await asyncio.gather(*self._dispatch_tasks, return_exceptions=True)
            self._dispatch_tasks.clear()

        # 4. 关闭写队列 + 等写循环排空（_write_queue.shutdown() 唤醒 _write_loop）
        self._write_queue.shutdown()
        if self._write_task is not None and not self._write_task.done():
            try:
                await self._write_task
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("写循环 task 关闭异常")

        # 5. 标记停止
        self._running = False


__all__ = ["WebBackendHost", "WebHostConfig"]
