"""
代理执行器模块
==============

本模块提供子代理派发和执行的核心功能，对齐标准 AgentTool 架构。

主要组件：
    - AgentExecutionContext: 代理运行时上下文
    - AgentAbortController: 代理中止控制器
    - TaskNotification: 任务通知数据类
    - run_agent_in_process: 进程内代理执行
    - run_agent_subprocess: 子进程代理执行
    - resolve_agent_tools: 根据代理定义组装工具池
    - format_task_notification / parse_task_notification: XML 序列化

架构概述：
    代理通过 AgentTool 派发，分为同步（前台）和异步（后台）两种模式。
    同步模式直接返回代理最终文本；异步模式通过 task-notification XML 通知完成。
    代理间通信通过内存中的 asyncio.Queue 实现。

使用示例：
    >>> from illusion.swarm.agent_executor import run_agent_in_process, AgentSpawnConfig
    >>> config = AgentSpawnConfig(...)
    >>> result = await run_agent_in_process(config, query_context)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import shlex
import shutil
import sys
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from illusion.coordinator.agent_definitions import AgentDefinition
from illusion.engine.messages import ConversationMessage
from illusion.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 代理中止控制器
# ---------------------------------------------------------------------------


class AgentAbortController:
    """代理的双重信号中止控制器。

    提供 *优雅* 取消（设置 ``cancel_event``；代理完成当前工具使用后退出）
    和 *强制* 终止（设置 ``force_cancel``；立即取消）。
    """

    def __init__(self) -> None:
        self.cancel_event: asyncio.Event = asyncio.Event()
        """设置为请求代理循环的优雅取消。"""

        self.force_cancel: asyncio.Event = asyncio.Event()
        """设置为请求立即（强制）终止。"""

        self._reason: str | None = None

    @property
    def is_cancelled(self) -> bool:
        """如果任一取消信号已设置则返回 True。"""
        return self.cancel_event.is_set() or self.force_cancel.is_set()

    def request_cancel(self, reason: str | None = None, *, force: bool = False) -> None:
        """请求取消代理。

        Args:
            reason: 取消的人类可读原因。
            force: 当为 True 时，设置 ``force_cancel`` 以立即终止。
        """
        self._reason = reason
        if force:
            self.force_cancel.set()
            self.cancel_event.set()
        else:
            self.cancel_event.set()

    @property
    def reason(self) -> str | None:
        """最近一次取消请求的原因。"""
        return self._reason


# ---------------------------------------------------------------------------
# 代理执行上下文
# ---------------------------------------------------------------------------

# 代理状态类型
AgentStatus = Literal["starting", "running", "idle", "stopped"]


@dataclass
class AgentExecutionContext:
    """代理运行时状态，存储在 ContextVar 中实现每个 asyncio Task 隔离。"""

    agent_id: str
    """唯一代理标识符。"""

    agent_name: str
    """人类可读名称，例如 ``"researcher"``。"""

    agent_definition: AgentDefinition | None = None
    """代理定义（如果使用 subagent_type 派发）。"""

    prompt: str = ""
    """代理的初始提示词。"""

    model: str | None = None
    """模型覆盖。"""

    cwd: Path = field(default_factory=lambda: Path.cwd())
    """工作目录。"""

    permission_mode: str | None = None
    """权限模式覆盖。"""

    abort_controller: AgentAbortController = field(default_factory=AgentAbortController)
    """中止控制器。"""

    message_queue: asyncio.Queue[TeammateMessage] = field(default_factory=asyncio.Queue)
    """回合之间传递的待处理消息队列。"""

    status: AgentStatus = "starting"
    """此代理的生命周期状态。"""

    started_at: float = field(default_factory=time.time)
    """代理生成时的 Unix 时间戳。"""

    tool_use_count: int = 0
    """此代理生命周期内调用的工具数量。"""

    total_tokens: int = 0
    """所有查询回合的累计 token 计数。"""

    output_file: Path | None = None
    """后台任务的输出文件路径。"""

    task_id: str | None = None
    """任务管理器中的任务 ID。"""


# 代理上下文变量
_agent_context_var: ContextVar[AgentExecutionContext | None] = ContextVar(
    "_agent_context_var", default=None
)


def get_agent_context() -> AgentExecutionContext | None:
    """返回当前运行的代理的 :class:`AgentExecutionContext`。"""
    return _agent_context_var.get()


def set_agent_context(ctx: AgentExecutionContext) -> None:
    """将 *ctx* 绑定到当前异步上下文。"""
    _agent_context_var.set(ctx)


# ---------------------------------------------------------------------------
# 活跃代理注册表（内存）
# ---------------------------------------------------------------------------

# 映射 agent_id -> AgentExecutionContext
_active_agents: dict[str, AgentExecutionContext] = {}


def get_active_agent(agent_id: str) -> AgentExecutionContext | None:
    """按 ID 查找活跃代理。"""
    return _active_agents.get(agent_id)


def get_active_agent_by_name(name: str) -> AgentExecutionContext | None:
    """按名称查找活跃代理。"""
    for ctx in _active_agents.values():
        if ctx.agent_name == name:
            return ctx
    return None


def list_active_agents() -> list[AgentExecutionContext]:
    """返回所有活跃代理。"""
    return list(_active_agents.values())


def _register_agent(ctx: AgentExecutionContext) -> None:
    """注册代理到活跃注册表。"""
    _active_agents[ctx.agent_id] = ctx


def _unregister_agent(agent_id: str) -> None:
    """从活跃注册表中移除代理。"""
    _active_agents.pop(agent_id, None)


# ---------------------------------------------------------------------------
# 消息类型
# ---------------------------------------------------------------------------


@dataclass
class TeammateMessage:
    """发送给代理的消息。"""

    text: str
    from_agent: str
    color: str | None = None
    timestamp: str | None = None
    summary: str | None = None


# ---------------------------------------------------------------------------
# 任务通知
# ---------------------------------------------------------------------------


@dataclass
class TaskNotification:
    """已完成代理任务的结构化结果。"""

    task_id: str
    """任务 ID。"""

    status: str
    """状态 (completed/failed/killed)。"""

    summary: str
    """人类可读的状态摘要。"""

    result: str | None = None
    """代理的最终文本响应。"""

    usage: dict[str, int] | None = None
    """使用统计信息。"""


# 使用统计字段名
_USAGE_FIELDS = ("total_tokens", "tool_uses", "duration_ms")


def format_task_notification(n: TaskNotification) -> str:
    """将 TaskNotification 序列化为标准 XML envelope。"""
    parts = [
        "<task-notification>",
        f"<task-id>{n.task_id}</task-id>",
        f"<status>{n.status}</status>",
        f"<summary>{n.summary}</summary>",
    ]
    if n.result is not None:
        parts.append(f"<result>{n.result}</result>")
    if n.usage:
        parts.append("<usage>")
        for key in _USAGE_FIELDS:
            if key in n.usage:
                parts.append(f"  <{key}>{n.usage[key]}</{key}>")
        parts.append("</usage>")
    parts.append("</task-notification>")
    return "\n".join(parts)


def parse_task_notification(xml: str) -> TaskNotification:
    """从 XML 字符串解析 TaskNotification。"""

    def _extract(tag: str) -> str | None:
        m = re.search(rf"<{tag}>(.*?)</{tag}>", xml, re.DOTALL)
        return m.group(1).strip() if m else None

    task_id = _extract("task-id") or ""
    status = _extract("status") or ""
    summary = _extract("summary") or ""
    result = _extract("result")

    usage: dict[str, int] | None = None
    usage_block = re.search(r"<usage>(.*?)</usage>", xml, re.DOTALL)
    if usage_block:
        usage = {}
        for key in _USAGE_FIELDS:
            m = re.search(rf"<{key}>(\d+)</{key}>", usage_block.group(1))
            if m:
                usage[key] = int(m.group(1))

    return TaskNotification(
        task_id=task_id,
        status=status,
        summary=summary,
        result=result,
        usage=usage,
    )


# ---------------------------------------------------------------------------
# 代理生成配置
# ---------------------------------------------------------------------------


@dataclass
class AgentSpawnConfig:
    """生成代理的配置。"""

    name: str
    """代理名称。"""

    prompt: str
    """代理的初始提示词。"""

    cwd: str
    """工作目录。"""

    agent_definition: AgentDefinition | None = None
    """代理定义。"""

    model: str | None = None
    """模型覆盖。"""

    parent_session_id: str = "main"
    """父会话 ID。"""

    permission_mode: str | None = None
    """权限模式覆盖。"""

    system_prompt: str | None = None
    """系统提示词覆盖。"""

    color: str | None = None
    """UI 颜色。"""


# ---------------------------------------------------------------------------
# 代理执行结果
# ---------------------------------------------------------------------------


@dataclass
class AgentResult:
    """代理执行的结果。"""

    agent_id: str
    """代理 ID。"""

    success: bool = True
    """是否成功完成。"""

    result_text: str = ""
    """代理的最终文本响应。"""

    error: str | None = None
    """错误信息（如果失败）。"""

    notification: TaskNotification | None = None
    """任务通知（用于异步模式）。"""

    total_tokens: int = 0
    """总 token 使用量。"""

    tool_use_count: int = 0
    """工具调用次数。"""

    duration_ms: int = 0
    """执行时长（毫秒）。"""


# ---------------------------------------------------------------------------
# 工具池解析
# ---------------------------------------------------------------------------

# 子代理默认禁止的工具
_AGENT_DISALLOWED_TOOLS = frozenset({
    "agent",  # 禁止递归派发
    "enter_plan_mode",
    "exit_plan_mode",
    "ask_user_question",
    "task_stop",
})


def resolve_agent_tools(
    agent_def: AgentDefinition | None,
    parent_registry: ToolRegistry,
) -> ToolRegistry:
    """根据代理定义组装工具池。

    Args:
        agent_def: 代理定义。如果为 None，使用所有工具。
        parent_registry: 父级工具注册表。

    Returns:
        ToolRegistry: 代理专用的工具注册表。
    """
    registry = ToolRegistry()

    # 确定允许的工具集
    if agent_def is None or agent_def.tools is None or agent_def.tools == ["*"]:
        # 使用所有工具
        allowed_names = None  # None 表示全部
    else:
        allowed_names = set(agent_def.tools)

    # 确定禁止的工具集
    disallowed = set(_AGENT_DISALLOWED_TOOLS)
    if agent_def and agent_def.disallowed_tools:
        disallowed.update(agent_def.disallowed_tools)

    # 从父注册表中筛选工具
    for tool in parent_registry.list_tools():
        # 跳过禁止的工具
        if tool.name in disallowed:
            continue
        # 如果指定了允许列表，只包含列表中的工具
        if allowed_names is not None and tool.name not in allowed_names:
            continue
        registry.register(tool)

    return registry


# ---------------------------------------------------------------------------
# 子进程命令构建
# ---------------------------------------------------------------------------

# 环境变量：覆盖代理命令
_AGENT_COMMAND_ENV_VAR = "ILLUSION_TEAMMATE_COMMAND"

# 要转发到子进程的环境变量
_AGENT_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_CODE_REMOTE",
    "CLAUDE_CODE_REMOTE_MEMORY_DIR",
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "NO_PROXY",
    "no_proxy",
    "SSL_CERT_FILE",
    "NODE_EXTRA_CA_CERTS",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "ILLUSION_API_FORMAT",
    "ILLUSION_BASE_URL",
    "ILLUSION_MODEL",
    "OPENAI_API_KEY",
]


def _get_agent_command() -> str:
    """返回用于生成代理子进程的可执行文件。"""
    override = os.environ.get(_AGENT_COMMAND_ENV_VAR)
    if override:
        return override

    entry_point = shutil.which("illusion")
    if entry_point:
        return entry_point

    return sys.executable


def _build_agent_cli_flags(
    *,
    model: str | None = None,
    permission_mode: str | None = None,
) -> list[str]:
    """构建从当前会话继承到子代理的 CLI 标志。"""
    flags: list[str] = ["--headless"]

    if permission_mode == "bypassPermissions":
        flags.append("--dangerously-skip-permissions")
    elif permission_mode == "acceptEdits":
        flags.extend(["--permission-mode", "acceptEdits"])

    if model:
        flags.extend(["--model", shlex.quote(model)])

    return flags


def _build_agent_env_vars() -> dict[str, str]:
    """构建要转发到子代理的环境变量。"""
    env: dict[str, str] = {
        "ILLUSION_AGENT_TEAMS": "1",
    }
    for key in _AGENT_ENV_VARS:
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


# ---------------------------------------------------------------------------
# 进程内代理执行
# ---------------------------------------------------------------------------


async def run_agent_in_process(
    config: AgentSpawnConfig,
    query_context: Any,
    parent_registry: ToolRegistry,
    *,
    is_async: bool = False,
    existing_context: AgentExecutionContext | None = None,
    on_progress: Any | None = None,
) -> AgentResult:
    """在当前进程中运行代理。

    此协程驱动查询引擎循环，直到代理完成或被取消。

    Args:
        config: 代理生成配置。
        query_context: 预构建的 QueryContext。
        parent_registry: 父级工具注册表（用于解析代理工具）。
        is_async: 是否为异步（后台）模式。

    Returns:
        AgentResult: 代理执行结果。
    """
    from illusion.engine.query import QueryContext
    from illusion.engine.stream_events import AssistantTextDelta, AssistantTurnComplete, ErrorEvent, ToolExecutionCompleted

    # 解析代理定义
    agent_def = config.agent_definition

    # 使用已有的上下文或创建新的
    if existing_context is not None:
        ctx = existing_context
        agent_id = ctx.agent_id
    else:
        agent_id = f"agent_{uuid.uuid4().hex[:12]}"
        ctx = AgentExecutionContext(
            agent_id=agent_id,
            agent_name=config.name,
            agent_definition=agent_def,
            prompt=config.prompt,
            model=config.model,
            cwd=Path(config.cwd),
            permission_mode=config.permission_mode or (agent_def.permission_mode if agent_def else None),
        )
        _register_agent(ctx)

    set_agent_context(ctx)

    # 解析工具池
    agent_tools = resolve_agent_tools(agent_def, parent_registry)

    # 构建系统提示词
    system_prompt = config.system_prompt
    if system_prompt is None and agent_def and agent_def.system_prompt:
        system_prompt = agent_def.system_prompt
    if system_prompt is None:
        system_prompt = query_context.system_prompt

    # 构建模型
    model = config.model
    if model is None and agent_def and agent_def.model:
        if agent_def.model == "inherit":
            model = query_context.model
        else:
            model = agent_def.model
    if model is None:
        model = query_context.model

    # 使用父级的权限检查器（agent 继承父级权限设置）
    permission_checker = query_context.permission_checker

    # 创建代理专用的 QueryContext（继承父级的权限和问答回调）
    agent_query_context = QueryContext(
        api_client=query_context.api_client,
        tool_registry=agent_tools,
        permission_checker=permission_checker,
        cwd=ctx.cwd,
        model=model,
        system_prompt=system_prompt,
        max_tokens=query_context.max_tokens,
        permission_prompt=query_context.permission_prompt,
        ask_user_prompt=query_context.ask_user_prompt,
        max_turns=agent_def.max_turns if agent_def and agent_def.max_turns else query_context.max_turns,
        hook_executor=None,  # agent 不执行 hooks
        effort=query_context.effort,
    )

    # 初始化消息列表
    messages: list[ConversationMessage] = [
        ConversationMessage.from_user_text(config.prompt)
    ]

    start_time = time.time()
    final_text = ""
    error_text = ""
    ctx.status = "running"

    logger.warning(
        "[agent_executor] %s: STARTING agent '%s' (model=%s, tools=%d, max_turns=%s, prompt=%.80s)",
        agent_id, config.name, model, len(agent_tools.list_tools()),
        agent_query_context.max_turns, config.prompt,
    )

    # Agent 超时时间（秒）
    AGENT_TIMEOUT = 300  # 5 分钟

    try:
        from illusion.engine.query import run_query

        async def _run_query_loop():
            """执行查询循环的内部协程。"""
            logger.warning("[agent_executor] %s: entering query loop", agent_id)
            event_count = 0
            async for event, usage in run_query(agent_query_context, messages):
                event_count += 1
                if event_count <= 3:
                    logger.warning("[agent_executor] %s: event #%d: %s", agent_id, event_count, type(event).__name__)
                # 检测错误事件
                if isinstance(event, ErrorEvent):
                    nonlocal error_text
                    error_text = event.message
                    logger.error("[agent_executor] %s: API error: %s", agent_id, error_text)
                    return

                # 跟踪文本增量（用于调试）
                if isinstance(event, AssistantTextDelta):
                    if not final_text:
                        logger.debug("[agent_executor] %s: received first text delta", agent_id)

                # 跟踪 token 使用
                if usage is not None:
                    with contextlib.suppress(AttributeError, TypeError):
                        ctx.total_tokens += getattr(usage, "input_tokens", 0)
                        ctx.total_tokens += getattr(usage, "output_tokens", 0)

                # 跟踪工具使用
                if isinstance(event, AssistantTurnComplete):
                    logger.debug(
                        "[agent_executor] %s: turn complete (tool_uses=%d)",
                        agent_id, len(event.message.tool_uses),
                    )

                # 转发工具事件为进度消息
                if on_progress is not None:
                    with contextlib.suppress(Exception):
                        if isinstance(event, ToolExecutionCompleted):
                            await on_progress(f"✓ {event.tool_name}")
                        elif hasattr(event, "tool_name"):
                            await on_progress(f"Running {event.tool_name}...")

                with contextlib.suppress(AttributeError, TypeError):
                    if getattr(event, "type", None) in ("tool_use", "tool_call", "ToolExecutionCompleted"):
                        ctx.tool_use_count += 1

                # 检查取消
                if ctx.abort_controller.is_cancelled:
                    logger.debug("[agent_executor] %s: cancelled", agent_id)
                    return

                # 耗尽消息队列
                while not ctx.message_queue.empty():
                    try:
                        queued = ctx.message_queue.get_nowait()
                        logger.debug("[agent_executor] %s: injecting message from %s", agent_id, queued.from_agent)
                        messages.append(ConversationMessage.from_user_text(queued.text))
                    except asyncio.QueueEmpty:
                        break

        # 带超时执行查询循环
        try:
            logger.warning("[agent_executor] %s: about to await query loop", agent_id)
            await asyncio.wait_for(_run_query_loop(), timeout=AGENT_TIMEOUT)
            logger.warning("[agent_executor] %s: query loop completed", agent_id)
        except asyncio.TimeoutError:
            logger.error("[agent_executor] %s: agent timed out after %ds", agent_id, AGENT_TIMEOUT)
            error_text = f"Agent timed out after {AGENT_TIMEOUT} seconds"

        # 从消息中提取最终文本
        for msg in reversed(messages):
            if msg.role == "assistant" and msg.content:
                text = msg.text
                if text:
                    final_text = text
                    break

        # 如果没有提取到文本，记录调试信息
        if not final_text and not error_text:
            assistant_count = sum(1 for m in messages if m.role == "assistant")
            logger.warning(
                "[agent_executor] %s: no text extracted (messages=%d, assistant_msgs=%d)",
                agent_id, len(messages), assistant_count,
            )
            # 尝试从所有助手消息中提取文本
            for msg in messages:
                if msg.role == "assistant":
                    text = msg.text
                    if text:
                        final_text = text
                        break

        ctx.status = "idle"

    except asyncio.CancelledError:
        logger.debug("[agent_executor] %s: task cancelled", agent_id)
        ctx.status = "stopped"
        raise
    except Exception as exc:
        logger.exception("[agent_executor] %s: unhandled exception", agent_id)
        ctx.status = "stopped"
        return AgentResult(
            agent_id=agent_id,
            success=False,
            error=str(exc),
            total_tokens=ctx.total_tokens,
            tool_use_count=ctx.tool_use_count,
            duration_ms=int((time.time() - start_time) * 1000),
        )
    finally:
        # 只有自己创建的 context 才注销，外部传入的由调用方负责注销
        if existing_context is None:
            _unregister_agent(agent_id)
        ctx.status = "stopped"

    duration_ms = int((time.time() - start_time) * 1000)

    # 如果有错误，返回错误结果
    if error_text and not final_text:
        return AgentResult(
            agent_id=agent_id,
            success=False,
            error=error_text,
            total_tokens=ctx.total_tokens,
            tool_use_count=ctx.tool_use_count,
            duration_ms=duration_ms,
        )

    logger.info(
        "[agent_executor] %s: completed (text_len=%d, tokens=%d, tools=%d, duration=%dms)",
        agent_id, len(final_text), ctx.total_tokens, ctx.tool_use_count, duration_ms,
    )

    # 构建任务通知
    notification = TaskNotification(
        task_id=agent_id,
        status="completed" if not ctx.abort_controller.is_cancelled else "killed",
        summary=f"Agent '{config.name}' completed",
        result=final_text,
        usage={
            "total_tokens": ctx.total_tokens,
            "tool_uses": ctx.tool_use_count,
            "duration_ms": duration_ms,
        },
    )

    return AgentResult(
        agent_id=agent_id,
        success=True,
        result_text=final_text,
        notification=notification,
        total_tokens=ctx.total_tokens,
        tool_use_count=ctx.tool_use_count,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# 子进程代理执行
# ---------------------------------------------------------------------------


async def run_agent_subprocess(
    config: AgentSpawnConfig,
) -> AgentResult:
    """作为子进程运行代理。

    Args:
        config: 代理生成配置。

    Returns:
        AgentResult: 代理执行结果（立即返回，代理在后台运行）。
    """
    agent_id = f"agent_{uuid.uuid4().hex[:12]}"
    agent_def = config.agent_definition

    # 构建 CLI 命令
    flags = _build_agent_cli_flags(
        model=config.model,
        permission_mode=config.permission_mode or (agent_def.permission_mode if agent_def else None),
    )
    extra_env = _build_agent_env_vars()
    env_prefix = " ".join(f"{k}={v!r}" for k, v in extra_env.items())

    agent_cmd = _get_agent_command()
    cmd_parts = [agent_cmd, "-m", "illusion"] + flags
    command = f"{env_prefix} {' '.join(cmd_parts)}" if env_prefix else " ".join(cmd_parts)

    # 创建任务
    from illusion.tasks.manager import get_task_manager

    manager = get_task_manager()
    try:
        record = await manager.create_agent_task(
            prompt=config.prompt,
            description=f"Agent: {config.name} ({agent_id})",
            cwd=config.cwd,
            task_type="local_agent",
            model=config.model,
            command=command,
        )
    except Exception as exc:
        logger.error("[agent_executor] Failed to spawn subprocess agent %s: %s", agent_id, exc)
        return AgentResult(
            agent_id=agent_id,
            success=False,
            error=str(exc),
        )

    logger.debug("[agent_executor] Spawned subprocess agent %s as task %s", agent_id, record.id)

    return AgentResult(
        agent_id=agent_id,
        success=True,
        # 子进程代理的结果通过 task notification 异步传递
    )


# ---------------------------------------------------------------------------
# 导出 TeammateMessage 供 send_message_tool 使用
# ---------------------------------------------------------------------------

__all__ = [
    "AgentAbortController",
    "AgentExecutionContext",
    "AgentResult",
    "AgentSpawnConfig",
    "AgentStatus",
    "TaskNotification",
    "TeammateMessage",
    "format_task_notification",
    "get_active_agent",
    "get_active_agent_by_name",
    "get_agent_context",
    "list_active_agents",
    "parse_task_notification",
    "resolve_agent_tools",
    "run_agent_in_process",
    "run_agent_subprocess",
    "set_agent_context",
]
