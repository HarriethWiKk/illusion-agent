"""核心工具感知查询循环。

本模块实现与模型交互的核心查询循环，支持工具调用和自动压缩功能。

主要功能：
    - 管理对话轮次和工具执行
    - 支持单工具和多工具调用
    - 自动压缩长对话历史
    - 执行权限检查和钩子

主要类和函数：
    - QueryContext: 查询上下文数据类
    - run_query: 异步生成器，运行对话循环
    - MaxTurnsExceeded: 超出最大轮次异常

使用示例：
    >>> from illusion.engine.query import QueryContext, run_query
    >>> async for event, usage in run_query(context, messages):
    ...     print(event)
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

from illusion.api.client import (
    ApiMessageCompleteEvent,
    ApiMessageRequest,
    ApiRetryEvent,
    ApiTextDeltaEvent,
    ApiToolCallStartedEvent,
    SupportsStreamingMessages,
)
from illusion.api.effort import EffortLevel
from illusion.api.usage import UsageSnapshot
from illusion.engine.messages import ConversationMessage, ContentBlock, MediaBlock, TextBlock, ThinkingBlock, ToolResultBlock, ToolUseBlock, _build_tool_result_content
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
from illusion.hooks import HookEvent, HookExecutor
from illusion.permissions.checker import PermissionChecker
from illusion.tools.base import ToolExecutionContext
from illusion.tools.base import ToolRegistry
from illusion.utils.file_state_cache import FileStateCache


# 权限提示回调类型：工具名称 -> 是否允许
PermissionPrompt = Callable[[str, str], Awaitable[bool]]
# 用户询问回调类型：(问题, 结构化选项数据) -> 回答
# questions 是 list[dict] 结构，含 question/header/options/multiSelect/noCustomInput
AskUserPrompt = Callable[[str, object], Awaitable[str]]
# 计划审批回调类型：计划内容 -> (是否允许, 反馈)
PlanApprovalPrompt = Callable[[str], Awaitable[tuple[bool, str]]]


class MaxTurnsExceeded(RuntimeError):
    """当智能体超出配置的最大轮次时抛出。

    Attributes:
        max_turns: 配置的最大轮次数量
    """

    def __init__(self, max_turns: int) -> None:
        super().__init__(f"Exceeded maximum turn limit ({max_turns})")
        self.max_turns = max_turns


class PermissionDenied(RuntimeError):
    """当用户拒绝工具权限时抛出，用于终止当前查询循环。

    Attributes:
        tool_name: 被拒绝的工具名称
        message: 拒绝原因描述
    """

    def __init__(self, tool_name: str, message: str = "") -> None:
        self.tool_name = tool_name
        super().__init__(message or f"Permission denied for {tool_name}")


def _synthesize_pending_tool_results(
    tool_calls: list[ToolUseBlock],
    tool_results_list: list[ToolResultBlock | None],
    error_message_fn: Callable[[str], str],
) -> list[ContentBlock]:
    """为未完成的工具调用合成 tool_result，避免孤立 tool_use。

    DeepSeek 等 strict OpenAI 兼容 provider 要求每个 tool_use 在紧接的下一条
    消息中有对应的 tool_result。权限拒绝/中断/异常等场景可能导致部分工具
    未执行完成，本函数为这些工具合成错误 tool_result。

    Args:
        tool_calls: 本轮所有 tool_use 块
        tool_results_list: 已收集的结果列表（可能短于 tool_calls，None 表示未完成）
        error_message_fn: 接受工具名称，返回合成错误消息文案的回调

    Returns:
        与 tool_calls 等长的 ToolResultBlock 列表（已完成的保留原结果，
        未完成的替换为合成错误结果）
    """
    # 单工具路径 tool_results_list 可能短于 tool_calls，补齐至等长再 zip。
    # 不修改入参列表，避免隐式副作用。
    padded = list(tool_results_list)
    padded.extend([None] * (len(tool_calls) - len(padded)))
    return [
        result if result is not None
        else ToolResultBlock(tool_use_id=tc.id, content=error_message_fn(tc.name), is_error=True)
        for tc, result in zip(tool_calls, padded)
    ]


# ---------------------------------------------------------------------------
# 后台代理完成通知
# ---------------------------------------------------------------------------


@dataclass
class BgAgentCompletion:
    """后台代理完成通知。

    当后台代理完成执行时，通过 BackgroundAgentTracker 传递给主查询循环。

    Attributes:
        agent_id: 代理 ID
        notification_xml: 格式化的任务通知 XML
    """

    agent_id: str
    notification_xml: str


class BackgroundAgentTracker:
    """追踪后台代理的完成状态，实现事件驱动的唤醒机制。

    当主 agent 派发后台代理后，无需轮询检查状态，而是通过
    asyncio.Event 等待后台代理完成通知，避免浪费 token。

    使用示例：
        >>> tracker = BackgroundAgentTracker()
        >>> tracker.register("agent_abc123")
        >>> # 后台代理完成时：
        >>> tracker.notify_completed("agent_abc123", "<task-notification>...</task-notification>")
        >>> # 主查询循环中：
        >>> completed = await tracker.wait_for_completion()
    """

    def __init__(self) -> None:
        self._wake_event: asyncio.Event = asyncio.Event()
        self._completions: list[BgAgentCompletion] = []
        self._pending_count: int = 0
        self._shutdown: bool = False
        # 强引用持有后台 task，防止 GC 在 task 完成前回收
        self._bg_tasks: set[asyncio.Task[None]] = set()
        # 最近一次活动时间戳（monotonic）。后台 agent 通过 on_progress 回调
        # 触发 notify_activity 刷新此值。wait_for_completion 据此判断是否
        # 因长时间无活动而退出 busy（agent 仍在运行，下轮 handle_line 续接）。
        self._last_activity: float = time.monotonic()

    def register(self, agent_id: str) -> None:
        """注册一个待处理的后台代理。

        Args:
            agent_id: 代理 ID
        """
        self._pending_count += 1
        # 注册即视为一次活动，避免刚启动就被 idle 超时误判
        self._last_activity = time.monotonic()

    def register_bg_task(self, task: asyncio.Task[None]) -> None:
        """注册一个后台 task 的强引用，shutdown 时统一 cancel。

        task 完成后自动从集合中移除，避免内存泄漏。

        Args:
            task: 后台 asyncio.Task
        """
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    def notify_activity(self, agent_id: str, message: str) -> None:
        """通知后台代理有活动（工具调用、文本生成等）。

        不改变 _pending_count，仅刷新 _last_activity。不 set wake_event，
        避免对每个 AssistantTextDelta 都空唤醒主循环（流式文本生成期间
        可能有数千个 delta）。

        wait_for_completion 的 idle 循环通过 wait_for(timeout=remaining)
        自动在剩余时间内唤醒重算：只要活动持续刷新 _last_activity，
        remaining 永远不会归零，主循环保持 busy。notify_completed 仍会
        set wake_event 立即唤醒主循环返回 completion。

        Args:
            agent_id: 代理 ID
            message: 活动描述（来自 on_activity 回调，仅用于调试）
        """
        if self._shutdown:
            return
        self._last_activity = time.monotonic()

    def notify_completed(self, agent_id: str, notification_xml: str) -> None:
        """通知后台代理已完成。

        shutdown 后调用为 no-op，避免在关闭后累积虚假 completion。
        重复 notify 不会使 _pending_count 变负（guard 生效）。

        每次调用都 set wake_event，唤醒 wait_for_completion（语义为"等待任意
        后台代理完成"）。原版 3cc12ba 即此行为，重构时误改为仅在 _pending_count
        归 0 时 set，导致多后台任务场景下第一个完成无法唤醒主 agent，主 agent
        只能等 30s 超时或所有任务完成。

        Args:
            agent_id: 代理 ID
            notification_xml: 格式化的任务通知 XML
        """
        if self._shutdown:
            return
        self._completions.append(
            BgAgentCompletion(agent_id=agent_id, notification_xml=notification_xml)
        )
        # guard 防止 _pending_count 变负（重复 notify 场景）
        self._pending_count = max(0, self._pending_count - 1)
        # 完成也是一次活动，刷新时间戳
        self._last_activity = time.monotonic()
        # 每次都 set wake_event：wait_for_completion 语义是"等待任意完成"，
        # 而非"等待全部完成"。drain 后 wake_event 会被 clear。
        self._wake_event.set()

    def has_pending(self) -> bool:
        """是否有待处理或已完成但未消费的后台代理。"""
        return self._pending_count > 0 or bool(self._completions)

    def _drain_completions(self) -> list[BgAgentCompletion]:
        """取出所有已完成的通知并重置唤醒事件。"""
        completions = list(self._completions)
        self._completions.clear()
        self._wake_event.clear()
        return completions

    def drain_now(self) -> list[BgAgentCompletion]:
        """非阻塞地取出所有已完成的通知。

        用于 mid-turn drain：工具执行后立即检查已完成的后台任务通知，
        不等待未完成的任务。对齐 Claude Code 的 query.ts drain gate。
        """
        return self._drain_completions()

    def shutdown(self) -> None:
        """关闭 tracker，cancel 所有 pending 后台 task 并唤醒等待者。

        多次调用安全（幂等）。shutdown 后 notify_completed 为 no-op，
        wait_for_completion 立即返回当前已收集的 completions。
        """
        self._shutdown = True
        # cancel 所有未完成的后台 task
        for task in list(self._bg_tasks):
            if not task.done():
                task.cancel()
        self._bg_tasks.clear()
        # 唤醒所有 wait_for_completion 等待者
        self._wake_event.set()

    async def wait_for_completion(
        self,
        timeout: float | None = None,
        idle_timeout: float | None = None,
    ) -> list[BgAgentCompletion]:
        """等待任意后台代理完成，返回所有已完成的通知。

        - 已 shutdown：立即返回当前 completions（不 drain）
        - 已有 completion：drain 并返回
        - 无 pending：返回空列表
        - 否则阻塞等待 wake_event

        两种超时模式：
            - timeout: 固定总超时（向后兼容）。超时后返回当前 completions（不 drain）。
            - idle_timeout: 无活动超时。后台 agent 通过 notify_activity 刷新
              _last_activity，只要持续有活动就一直等待，仅当长时间无活动时
              才返回空列表（agent 仍在运行，下轮 handle_line 续接）。

        Args:
            timeout: 固定总超时秒数，None 表示不限制（与 idle_timeout 互斥）。
                向后兼容用途，新代码应优先使用 idle_timeout。
            idle_timeout: 无活动超时秒数，None 表示不启用活动感知模式。
                启用后：有 completion 立即返回；无 completion 但有活动则继续等；
                无活动超过 idle_timeout 才返回空列表。

        Returns:
            list[BgAgentCompletion]: 已完成的后台代理通知列表
        """
        # shutdown 后立即返回当前 completions（不 drain，因为已关闭）
        if self._shutdown:
            return list(self._completions)
        if self._completions:
            return self._drain_completions()
        if self._pending_count <= 0:
            return []

        # 活动感知模式：循环等待，有活动就刷新，idle 超时才退出
        # wake_event 仅由 notify_completed/shutdown 触发；notify_activity
        # 只刷新 _last_activity，不 set event（避免高频空唤醒）。
        # 因此 wait_for 超时后需重新计算 remaining：若活动持续刷新，
        # remaining 永远不会归零，循环继续 wait；仅当真 idle 超时才退出。
        if idle_timeout is not None:
            while not self._shutdown and self._pending_count > 0:
                if self._completions:
                    return self._drain_completions()
                # 计算剩余 idle 时间
                remaining = idle_timeout - (time.monotonic() - self._last_activity)
                if remaining <= 0:
                    # idle 超时：返回当前 completions（不 drain），agent 仍存活
                    return list(self._completions)
                try:
                    await asyncio.wait_for(self._wake_event.wait(), timeout=remaining)
                    # wake_event 被 set：可能是 completion 或 shutdown
                    # 循环顶部会重新检查 _completions 和 _shutdown
                except asyncio.TimeoutError:
                    # wait_for 自然超时：可能是真 idle 超时，或活动刷新了
                    # _last_activity 但未 set event。重新循环计算 remaining。
                    # 若 _completions 在此期间到达（notify_completed 会 set event，
                    # 不会走到这里），优先处理 completion。
                    if self._completions:
                        return self._drain_completions()
                    # 继续循环：若 remaining 仍 > 0（活动刷新过），重新 wait；
                    # 若 remaining <= 0（真 idle 超时），循环顶部返回。
                    continue
            # shutdown 或 pending 归零
            if self._shutdown:
                return list(self._completions)
            return self._drain_completions() if self._completions else []

        # 固定总超时模式（向后兼容）
        try:
            if timeout is not None:
                await asyncio.wait_for(self._wake_event.wait(), timeout=timeout)
            else:
                await self._wake_event.wait()
        except asyncio.TimeoutError:
            # 超时返回当前 completions（不 drain），tracker 仍可继续使用
            return list(self._completions)
        # 等待期间发生 shutdown：返回当前 completions（不 drain）
        if self._shutdown:
            return list(self._completions)
        return self._drain_completions()


@dataclass
class QueryContext:
    """跨查询运行的共享上下文。

    包含执行查询所需的所有配置信息，包括API客户端、
    工具注册表、权限检查器等。

    Attributes:
        api_client: 支持流式消息的API客户端
        tool_registry: 工具注册表
        permission_checker: 权限检查器
        cwd: 当前工作目录
        model: 模型名称
        system_prompt: 系统提示词
        max_tokens: 最大令牌数
        permission_prompt: 权限提示回调（可选）
        ask_user_prompt: 用户询问回调（可选）
        max_turns: 最大轮次限制（可选）
        hook_executor: 钩子执行器（可选）
        tool_metadata: 工具元数据（可选）
        effort: 推理强度级别（可选）
    """

    api_client: SupportsStreamingMessages
    tool_registry: ToolRegistry
    permission_checker: PermissionChecker
    cwd: Path
    model: str
    system_prompt: str
    max_tokens: int
    permission_prompt: PermissionPrompt | None = None
    ask_user_prompt: AskUserPrompt | None = None
    plan_approval_prompt: PlanApprovalPrompt | None = None
    max_turns: int | None = 200
    hook_executor: HookExecutor | None = None
    tool_metadata: dict[str, object] | None = None
    effort: EffortLevel | None = None
    bg_agent_tracker: BackgroundAgentTracker | None = None
    bg_agent_wait_timeout: float = 300.0  # 后台代理 idle 超时阈值（秒），与前台 IDLE_TIMEOUT 一致
    compact_state: Any = None  # AutoCompactState，从 QueryEngine 传入
    # 文件历史回调：工具执行前调用，参数为 (工具名称, 工具输入)
    on_before_tool_execute: Callable[[str, dict[str, Any]], None] | None = None
    # 文件状态缓存：用于读写去重和 mtime 检测
    file_state_cache: FileStateCache | None = None
    # 工具进度消息队列：工具执行过程中通过 on_progress 回调上报进度，
    # run_query 主循环 drain 此队列并 yield ToolProgressEvent。
    # 元素为 (tool_use_id, message)。仅单工具路径使用（agent 工具前台模式），
    # 每轮工具执行前由 run_query 重置。
    # 多工具并发路径不支持进度追踪：as_completed 按完成顺序 yield，主循环无法
    # 并发 drain 队列；且并发场景下进度消息意义有限（用户更关心整体完成情况）。
    # 如需支持，需改造为 wait(FIRST_COMPLETED) + 共享队列（消息带 tool_use_id 区分）。
    progress_queue: asyncio.Queue[tuple[str, str]] | None = None


async def run_query(
    context: QueryContext,
    messages: list[ConversationMessage],
) -> AsyncIterator[tuple[StreamEvent, UsageSnapshot | None]]:
    """运行对话循环直到模型停止请求工具。

    在每个轮次开始时检查自动压缩。当估计的令牌数超过
    模型的自动压缩阈值时，引擎首先尝试廉价的微压缩
    （清除旧的工具结果内容），如果还不够，则执行基于LLM
    的旧消息摘要。

    Args:
        context: 查询上下文
        messages: 对话消息列表

    Yields:
        tuple[StreamEvent, UsageSnapshot | None]: 流事件和可选的使用量快照

    使用示例：
        >>> context = QueryContext(...)
        >>> messages = [ConversationMessage.from_user_text("你好")]
        >>> async for event, usage in run_query(context, messages):
        ...     print(event)
    """
    from illusion.config.i18n import t
    from illusion.services.compact import (
        AutoCompactState,
        auto_compact_if_needed,
        calculate_token_warning_state,
        reactive_compact,
    )

    # 使用从 QueryEngine 传入的持久化压缩状态
    compact_state: AutoCompactState = context.compact_state or AutoCompactState()

    turn_count = 0  # 轮次计数器
    while context.max_turns is None or turn_count < context.max_turns:
        turn_count += 1

        # --- 上下文警告检查 ---------------
        if not compact_state.warning_suppressed:
            warning = calculate_token_warning_state(messages, context.model)
            if warning.is_above_warning_threshold and not warning.is_above_autocompact_threshold:
                pct = int(warning.estimated_tokens * 100 / warning.context_window) if warning.context_window > 0 else 0
                yield StatusEvent(
                    message=t("compact_warning_approaching", pct=pct)
                ), None
        # 压缩后重置警告抑制（下次微压缩时清除）
        if compact_state.warning_suppressed:
            compact_state.warning_suppressed = False

        # --- 调用模型前检查自动压缩 ---------------
        messages, was_compacted = await auto_compact_if_needed(
            messages,
            api_client=context.api_client,
            model=context.model,
            system_prompt=context.system_prompt,
            state=compact_state,
        )
        if was_compacted:
            yield StatusEvent(message=t("compact_compacted")), None
        # ---------------------------------------------------------------

        final_message: ConversationMessage | None = None
        usage = UsageSnapshot()

        try:
            # 流式请求模型响应
            async for event in context.api_client.stream_message(  # type: ignore[attr-defined]
                ApiMessageRequest(
                    model=context.model,
                    messages=messages,
                    system_prompt=context.system_prompt,
                    max_tokens=context.max_tokens,
                    tools=context.tool_registry.to_api_schema(),
                    effort=context.effort,
                )
            ):
                if isinstance(event, ApiTextDeltaEvent):
                    # 输出助手文本增量事件
                    yield AssistantTextDelta(
                        text=event.text,
                        reasoning=event.reasoning,
                    ), None
                    continue
                if isinstance(event, ApiRetryEvent):
                    # 输出状态事件：重试信息
                    yield StatusEvent(
                        message=(
                            f"Request failed; retrying in {event.delay_seconds:.1f}s "
                            f"(attempt {event.attempt + 1} of {event.max_attempts}): {event.message}"
                        )
                    ), None
                    continue
                if isinstance(event, ApiToolCallStartedEvent):
                    # 模型开始生成工具调用时立即通知前端，无需等待完整参数
                    yield ToolExecutionStarted(
                        tool_name=event.tool_name,
                        tool_input={},
                        tool_use_id=event.tool_use_id,
                    ), None
                    continue

                if isinstance(event, ApiMessageCompleteEvent):
                    final_message = event.message
                    usage = event.usage
        except Exception as exc:
            error_msg = str(exc)
            error_lower = error_msg.lower()

            # --- 响应式压缩：prompt-too-long 时尝试压缩重试 ---
            if "prompt" in error_lower and "long" in error_lower:
                yield StatusEvent(message=t("compact_overflow_detected")), None
                messages, was_compacted = await reactive_compact(
                    messages,
                    api_client=context.api_client,
                    model=context.model,
                    system_prompt=context.system_prompt,
                )
                if was_compacted:
                    yield StatusEvent(message=t("compact_reactive_success")), None
                    # 重试当前轮次（不增加 turn_count）
                    turn_count -= 1
                    continue
                # 压缩也失败，报错
                yield ErrorEvent(message=t("compact_overflow_failed", error=error_msg)), None
                return

            # 检查是否为网络相关错误
            if "connect" in error_lower or "timeout" in error_lower or "network" in error_lower:
                yield ErrorEvent(message=t("compact_network_error", error=error_msg)), None
            else:
                yield ErrorEvent(message=t("compact_api_error", error=error_msg)), None
            return

        if final_message is None:
            raise RuntimeError("Model stream finished without a final message")

        # 添加助手消息到历史记录
        messages.append(final_message)

        yield AssistantTurnComplete(message=final_message, usage=usage), usage

        # 如果没有工具调用，检查是否有待处理的后台代理
        if not final_message.tool_uses:
            tracker = context.bg_agent_tracker
            if tracker is not None and tracker.has_pending():
                # 发出等待状态事件（显示在 shimmer 区域）
                from illusion.config.i18n import t as _t
                yield StatusEvent(message=_t("bg_agent_waiting"), bg_agent=True), None
                # 等待后台代理完成：使用 idle 超时模式，只要代理持续有活动
                # （工具调用、文本生成等）就保持 busy，仅当长时间无活动时才退出。
                # bg_agent_wait_timeout 语义从"固定 300s 超时"改为"idle 超时阈值"。
                completed = await tracker.wait_for_completion(
                    idle_timeout=context.bg_agent_wait_timeout
                )
                if completed:
                    # 将完成通知注入为用户消息，触发模型继续处理
                    notification_parts = [c.notification_xml for c in completed]
                    notification_text = "\n\n".join(notification_parts)
                    messages.append(ConversationMessage.from_user_text(notification_text))
                    yield StatusEvent(message=_t("bg_agent_resuming"), bg_agent=True), None
                    continue

            # 执行 Stop 钩子（对齐 Claude Code）
            if context.hook_executor is not None:
                last_msg_text = final_message.text if final_message else ""
                stop_result = await context.hook_executor.execute(
                    HookEvent.STOP,
                    {"stop_hook_active": False, "last_assistant_message": last_msg_text},
                )
                # blockingError 注入为用户消息继续对话
                if stop_result.blocked:
                    messages.append(ConversationMessage.from_user_text(
                        f"[Hook] {stop_result.reason}"
                    ))
                    continue
                # preventContinuation 停止循环
                if stop_result.prevent_continuation:
                    return
                # additionalContext 注入
                for ctx in stop_result.additional_contexts:
                    if ctx:
                        messages.append(ConversationMessage.from_user_text(
                            _wrap_in_system_reminder(ctx)
                        ))
            return

        tool_calls = final_message.tool_uses

        # 输出工具链开始事件
        yield ToolChainStarted(tool_count=len(tool_calls)), None

        tool_results_list: list[ToolResultBlock | None] = []
        # 收集钩子 additionalContext，工具执行完成后合并到 tool_result 消息中。
        # 不能作为独立 user(text) 消息插入到 assistant(tool_use) 和 user(tool_result)
        # 之间，否则会破坏 tool_use→tool_result 紧邻不变量，导致 DeepSeek 等
        # strict provider 返回 400 "tool_use ids were found without tool_result"。
        all_hook_ctxs: list[str] = []
        try:
            if len(tool_calls) == 1:
                # 单个工具：顺序执行
                tc = tool_calls[0]
                yield ToolExecutionStarted(tool_name=tc.name, tool_input=tc.input, tool_use_id=tc.id), None
                # 创建进度队列（仅单工具路径使用，用于 agent 工具前台模式上报子代理工具调用进度）
                context.progress_queue = asyncio.Queue()
                try:
                    exec_task = asyncio.ensure_future(
                        _execute_tool_call(context, tc.name, tc.id, tc.input)
                    )
                    # 工具执行期间产生的进度消息实时 yield
                    while not exec_task.done():
                        get_task = asyncio.ensure_future(context.progress_queue.get())
                        done, _ = await asyncio.wait(
                            {exec_task, get_task}, return_when=asyncio.FIRST_COMPLETED
                        )
                        if get_task in done and not get_task.cancelled():
                            tid, msg = get_task.result()
                            yield ToolProgressEvent(tool_use_id=tid, message=msg), None
                        else:
                            # exec_task 先完成，取消未完成的 get_task
                            get_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await get_task
                    # drain 工具执行完成后队列中剩余的进度消息
                    while not context.progress_queue.empty():
                        tid, msg = context.progress_queue.get_nowait()
                        yield ToolProgressEvent(tool_use_id=tid, message=msg), None
                    # 获取结果（如有异常会重新抛出，由外层 except 处理）
                    result, hook_ctxs = exec_task.result()
                finally:
                    context.progress_queue = None
                all_hook_ctxs.extend(hook_ctxs)
                yield ToolExecutionCompleted(
                    tool_name=tc.name,
                    output=result.text_content,
                    is_error=result.is_error,
                    tool_use_id=tc.id,
                ), None
                tool_results_list.append(result)
            else:
                # 多个工具：并发执行
                # 注意：此路径不创建 progress_queue，故 _execute_tool_call 注入的
                # on_progress 为 None，agent 工具前台模式在并发场景下不会上报子代理
                # 进度。这是设计决策（见 QueryContext.progress_queue 注释）。
                for tc in tool_calls:
                    # 始终发送带完整 tool_input 的 ToolExecutionStarted，
                    # 由下游（backend_host）通过 tool_use_id 去重避免前端重复显示
                    yield ToolExecutionStarted(tool_name=tc.name, tool_input=tc.input, tool_use_id=tc.id), None

                async def _safe_run(idx: int, tc: ToolUseBlock) -> tuple[int, ToolResultBlock, list[Any]]:
                    """并发执行单个工具，捕获非权限异常转为错误结果。"""
                    try:
                        result, hook_ctxs = await _execute_tool_call(context, tc.name, tc.id, tc.input)
                        return idx, result, hook_ctxs
                    except PermissionDenied:
                        raise
                    except Exception as exc:
                        return idx, ToolResultBlock(
                            tool_use_id=tc.id,
                            content=f"Tool {tc.name} failed: {exc}",
                            is_error=True,
                        ), []

                # 并发执行所有工具调用，每个工具完成后立即发送完成事件
                tool_results_list = [None] * len(tool_calls)
                tasks = [
                    asyncio.ensure_future(_safe_run(i, tc))
                    for i, tc in enumerate(tool_calls)
                ]
                try:
                    for coro in asyncio.as_completed(tasks):
                        idx, result, hook_ctxs = await coro
                        all_hook_ctxs.extend(hook_ctxs)
                        tool_results_list[idx] = result
                        yield ToolExecutionCompleted(
                            tool_name=tool_calls[idx].name,
                            output=result.text_content,
                            is_error=result.is_error,
                            tool_use_id=tool_calls[idx].id,
                        ), None
                finally:
                    # ⚠️ 关键：取消所有未完成 task，避免孤儿 task 泄漏
                    pending = [t for t in tasks if not t.done()]
                    for t in pending:
                        t.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
        except PermissionDenied as exc:
            from illusion.config.i18n import t

            denied_tool_name = exc.tool_name  # 捕获到局部变量，避免 lambda 闭包引用 exc

            # 为所有未完成的工具合成 tool_result，确保消息历史一致
            synth = _synthesize_pending_tool_results(
                tool_calls,
                tool_results_list,
                error_message_fn=lambda name: (
                    f"Permission denied for {name}"
                    if name == denied_tool_name
                    else f"Tool {name} interrupted"
                ),
            )
            # 中断前已完成工具的钩子上下文也需追加，避免丢失
            for ctx in all_hook_ctxs:
                synth.append(TextBlock(text=_wrap_in_system_reminder(ctx)))
            messages.append(ConversationMessage(role="user", content=synth))
            yield ErrorEvent(message=t("permission_denied_stopped", tool=exc.tool_name)), None
            return
        except (KeyboardInterrupt, asyncio.CancelledError):
            # Ctrl+C / Escape 取消 / 模型切换等中断场景：
            # assistant 消息（含 tool_use）已入列，但 tool_result 未追加。
            # 合成错误结果保持历史一致性，防止下一轮 API 返回 400。
            synth = _synthesize_pending_tool_results(
                tool_calls,
                tool_results_list,
                error_message_fn=lambda name: f"Tool {name} interrupted",
            )
            # 中断前已完成工具的钩子上下文也需追加，避免丢失
            for ctx in all_hook_ctxs:
                synth.append(TextBlock(text=_wrap_in_system_reminder(ctx)))
            messages.append(ConversationMessage(role="user", content=synth))
            raise
        except Exception:  # noqa: BLE001
            # 能到达此 handler 的例外路径：
            #   - 单工具路径 _execute_tool_call 内部工具实现抛出非预期异常
            #     （如 RuntimeError、OSError、文件系统错误），未经 _safe_run
            #     包裹故直接传播至此；
            #   - 多工具路径 asyncio.as_completed 自身可能因取消/超时竞态
            #     抛出异常（非工具返回值）；
            #   - 其他运行时意外（内存不足等）。
            # 多工具路径中单个工具的异常已被 _safe_run 捕获并转为 error
            # ToolResultBlock，不会到达此 handler。
            # 合成 tool_result 后重新抛出，保持消息历史一致性。
            synth = _synthesize_pending_tool_results(
                tool_calls,
                tool_results_list,
                error_message_fn=lambda name: f"Tool {name} interrupted",
            )
            # 中断前已完成工具的钩子上下文也需追加，避免丢失
            for ctx in all_hook_ctxs:
                synth.append(TextBlock(text=_wrap_in_system_reminder(ctx)))
            messages.append(ConversationMessage(role="user", content=synth))
            raise

        # 输出工具链完成事件
        yield ToolChainCompleted(
            results_summary=[
                {"name": tc.name, "is_error": result.is_error}
                for tc, result in zip(tool_calls, tool_results_list)
                if result is not None
            ]
        ), None

        # 将工具结果作为用户消息添加到历史记录
        # 钩子 additionalContext 合并到同一 user 消息中（作为 TextBlock 追加在
        # tool_result 之后），保持 tool_use→tool_result 紧邻不变量。
        all_results: list[TextBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock | MediaBlock] = [r for r in tool_results_list if r is not None]
        for ctx in all_hook_ctxs:
            all_results.append(TextBlock(text=_wrap_in_system_reminder(ctx)))
        messages.append(ConversationMessage(role="user", content=all_results))

        # ------------------------------------------------------------------
        # Mid-turn drain：工具执行后立即检查已完成的后台任务通知
        # 对齐 Claude Code 的 query.ts drain gate（line 1566-1590）：
        # 每轮工具执行后，drain 已完成但未消费的通知，注入为 user message，
        # 让 LLM 在下一轮调用时看到通知，无需轮询 task_output/sleep。
        # ------------------------------------------------------------------
        tracker = context.bg_agent_tracker
        if tracker is not None:
            completed = tracker.drain_now()
            if completed:
                notification_parts = [c.notification_xml for c in completed]
                notification_text = "\n\n".join(notification_parts)
                messages.append(ConversationMessage.from_user_text(notification_text))
                yield StatusEvent(message=t("bg_agent_resuming"), bg_agent=True), None

    # 超出最大轮次限制
    if context.max_turns is not None:
        raise MaxTurnsExceeded(context.max_turns)
    raise RuntimeError("Query loop exited without a max_turns limit or final response")


async def _execute_tool_call(
    context: QueryContext,
    tool_name: str,
    tool_use_id: str,
    tool_input: dict[str, object],
) -> tuple[ToolResultBlock, list[str]]:
    """执行单个工具调用。

    Returns:
        (工具执行结果, additionalContexts 列表)
    """
    hook_additional_contexts: list[str] = []

    # 执行预工具钩子（对齐 Claude Code PreToolUse 输入格式）
    if context.hook_executor is not None:
        pre_hooks = await context.hook_executor.execute(
            HookEvent.PRE_TOOL_USE,
            {"tool_name": tool_name, "tool_input": tool_input, "tool_use_id": tool_use_id},
        )
        if pre_hooks.blocked:
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=pre_hooks.reason or f"PreToolUse hook blocked {tool_name}",
                is_error=True,
            ), hook_additional_contexts
        # updatedInput：钩子可修改工具输入
        if pre_hooks.updated_input:
            tool_input = pre_hooks.updated_input
        # 收集 additionalContext
        hook_additional_contexts.extend(pre_hooks.additional_contexts)

    # 从注册表获取工具
    tool = context.tool_registry.get(tool_name)
    if tool is None:
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=f"Unknown tool: {tool_name}",
            is_error=True,
        ), hook_additional_contexts

    # 验证工具输入参数
    try:
        parsed_input = tool.input_model.model_validate(tool_input)
    except Exception as exc:
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=f"Invalid input for {tool_name}: {exc}",
            is_error=True,
        ), hook_additional_contexts

    # 在权限检查前规范化通用工具输入，以便路径规则一致地应用于使用 `file_path` 或 `path` 的内置工具
    _file_path = _resolve_permission_file_path(context.cwd, tool_input, parsed_input)
    _command = _extract_permission_command(tool_input, parsed_input)
    # 评估权限
    decision = context.permission_checker.evaluate(
        tool_name,
        is_read_only=tool.is_read_only(parsed_input),
        file_path=_file_path,
        command=_command,
    )
    if not decision.allowed:
        # 系统自动阻止（如计划模式）：返回错误结果给模型，不终止查询循环
        if decision.auto_blocked:
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=f"[Permission blocked] {decision.reason or f'{tool_name} is not allowed in current mode'}",
                is_error=True,
            ), hook_additional_contexts
        # 沙箱限制阻止：向用户询问三选项确认
        if decision.sandbox_blocked and context.ask_user_prompt is not None:
            from illusion.config.i18n import _is_zh
            from illusion.config.settings import load_settings as _load_settings
            _locale = _load_settings().ui_language or "en"
            _is_cn = _is_zh(_locale)

            denied_path = decision.sandbox_denied_path or "unknown"
            if _is_cn:
                question_text = (
                    f"沙箱限制：「{denied_path}」被沙箱配置阻止。\n"
                    f"工具：{tool_name}\n"
                    f"是否允许此操作？"
                )
                questions_data = [
                    {
                        "question": f"允许访问「{denied_path}」？",
                        "header": "沙箱",
                        "options": [
                            {"label": "允许", "description": "允许本次操作"},
                            {"label": "当前会话允许", "description": "允许此路径在当前会话中访问（重启后失效）"},
                            {"label": "拒绝", "description": "阻止此操作"},
                        ],
                        "multiSelect": False,
                        "noCustomInput": True,
                    }
                ]
            else:
                question_text = (
                    f"Sandbox restriction: '{denied_path}' is blocked by sandbox configuration.\n"
                    f"Tool: {tool_name}\n"
                    f"Do you want to allow this operation?"
                )
                questions_data = [
                    {
                        "question": f"Allow access to '{denied_path}'?",
                        "header": "Sandbox",
                        "options": [
                            {"label": "Allow", "description": "Allow this single operation"},
                            {"label": "Allow for session", "description": "Allow this path for the current session (not persistent)"},
                            {"label": "Deny", "description": "Block this operation"},
                        ],
                        "multiSelect": False,
                        "noCustomInput": True,
                    }
                ]
            answer = await context.ask_user_prompt(question_text, questions_data)
            # 解析用户选择
            answer_str = str(answer).strip() if answer else ""
            if "Allow for session" in answer_str or "当前会话允许" in answer_str:
                # 会话级允许
                context.permission_checker.allow_sandbox_path_for_session(denied_path)
            elif "Allow" in answer_str or "允许" in answer_str:
                # 单次允许（不做任何持久化）
                pass
            else:
                # 拒绝
                raise PermissionDenied(tool_name, f"Sandbox denied: {denied_path}")
        # 需要用户确认
        elif decision.requires_confirmation and context.permission_prompt is not None:
            confirmed = await context.permission_prompt(tool_name, decision.reason)
            if not confirmed:
                raise PermissionDenied(tool_name, f"Permission denied for {tool_name}")
        else:
            raise PermissionDenied(tool_name, decision.reason or f"Permission denied for {tool_name}")

    # 文件历史：工具执行前回调（备份即将被修改的文件）
    if context.on_before_tool_execute is not None:
        context.on_before_tool_execute(tool_name, tool_input)

    # 进度回调：将进度消息入队（仅当 progress_queue 存在时，即单工具路径）。
    # agent 工具前台模式通过此回调上报子代理的工具调用进度。
    async def _emit_progress(message: str) -> None:
        if context.progress_queue is not None:
            await context.progress_queue.put((tool_use_id, message))

    # 执行工具
    result = await tool.execute(
        parsed_input,
        ToolExecutionContext(
            cwd=context.cwd,
            metadata={
                "tool_registry": context.tool_registry,
                "ask_user_prompt": context.ask_user_prompt,
                "plan_approval_prompt": context.plan_approval_prompt,
                "permission_checker": context.permission_checker,
                "file_state_cache": context.file_state_cache,
                **(context.tool_metadata or {}),
            },
            on_progress=_emit_progress if context.progress_queue is not None else None,
        ),
    )
    # 处理工具请求的 CWD 切换（如 enter_worktree）
    if result.metadata.get("new_cwd"):
        context.cwd = Path(result.metadata["new_cwd"])
    tool_result = ToolResultBlock(
        tool_use_id=tool_use_id,
        content=_build_tool_result_content(result.output, result.metadata),
        is_error=result.is_error,
    )
    # 执行后工具钩子（对齐 Claude Code PostToolUse/PostToolUseFailure）
    if context.hook_executor is not None:
        hook_event = HookEvent.POST_TOOL_USE_FAILURE if tool_result.is_error else HookEvent.POST_TOOL_USE
        post_hooks = await context.hook_executor.execute(
            hook_event,
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_response": tool_result.text_content,
                "tool_use_id": tool_use_id,
            },
        )
        hook_additional_contexts.extend(post_hooks.additional_contexts)
    return tool_result, hook_additional_contexts


def _resolve_permission_file_path(
    cwd: Path,
    raw_input: dict[str, object],
    parsed_input: object,
) -> str | None:
    """解析权限检查所需的文件路径。

    尝试从原始输入和解析后的输入中提取文件路径。

    Args:
        cwd: 当前工作目录
        raw_input: 原始工具输入
        parsed_input: 解析后的工具输入

    Returns:
        str | None: 解析后的绝对文件路径，如果没有则返回None
    """
    # 首先检查原始输入中的 file_path 或 path
    for key in ("file_path", "path"):
        value = raw_input.get(key)
        if isinstance(value, str) and value.strip():
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = cwd / path
            return str(path.resolve())

    # 然后检查解析后输入的属性
    for attr in ("file_path", "path"):
        value = getattr(parsed_input, attr, None)
        if isinstance(value, str) and value.strip():
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = cwd / path
            return str(path.resolve())

    return None


def _extract_permission_command(
    raw_input: dict[str, object],
    parsed_input: object,
) -> str | None:
    """提取权限检查所需的命令。

    尝试从原始输入和解析后的输入中提取命令。

    Args:
        raw_input: 原始工具输入
        parsed_input: 解析后的工具输入

    Returns:
        str | None: 命令字符串，如果没有则返回None
    """
    # 首先检查原始输入中的 command
    value = raw_input.get("command")
    if isinstance(value, str) and value.strip():
        return value

    # 然后检查解析后输入的 command 属性
    value = getattr(parsed_input, "command", None)
    if isinstance(value, str) and value.strip():
        return value

    return None


def _wrap_in_system_reminder(content: str) -> str:
    """向后兼容别名。"""
    from illusion.hooks.utils import wrap_in_system_reminder
    return wrap_in_system_reminder(content)
