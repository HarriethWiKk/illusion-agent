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
from illusion.engine.messages import ConversationMessage, MediaBlock, TextBlock, ThinkingBlock, ToolResultBlock, ToolUseBlock, _build_tool_result_content
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

    def register(self, agent_id: str) -> None:
        """注册一个待处理的后台代理。

        Args:
            agent_id: 代理 ID
        """
        self._pending_count += 1

    def notify_completed(self, agent_id: str, notification_xml: str) -> None:
        """通知后台代理已完成。

        Args:
            agent_id: 代理 ID
            notification_xml: 格式化的任务通知 XML
        """
        self._completions.append(BgAgentCompletion(agent_id=agent_id, notification_xml=notification_xml))
        self._pending_count -= 1
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

    async def wait_for_completion(self) -> list[BgAgentCompletion]:
        """等待任意后台代理完成，返回所有已完成的通知。

        如果已有完成的通知则立即返回，否则阻塞等待。

        Returns:
            list[BgAgentCompletion]: 已完成的后台代理通知列表
        """
        if self._completions:
            return self._drain_completions()
        if self._pending_count <= 0:
            return []
        await self._wake_event.wait()
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
    compact_state: Any = None  # AutoCompactState，从 QueryEngine 传入
    # 文件历史回调：工具执行前调用，参数为 (工具名称, 工具输入)
    on_before_tool_execute: Callable[[str, dict[str, Any]], None] | None = None
    # 文件状态缓存：用于读写去重和 mtime 检测
    file_state_cache: FileStateCache | None = None


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
                # 等待任意后台代理完成（不消耗 token）
                completed = await tracker.wait_for_completion()
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
        try:
            if len(tool_calls) == 1:
                # 单个工具：顺序执行
                tc = tool_calls[0]
                yield ToolExecutionStarted(tool_name=tc.name, tool_input=tc.input, tool_use_id=tc.id), None
                result, hook_ctxs = await _execute_tool_call(context, tc.name, tc.id, tc.input)
                # 注入钩子 additionalContext 为独立的 user message
                for ctx in hook_ctxs:
                    messages.append(ConversationMessage.from_user_text(_wrap_in_system_reminder(ctx)))
                yield ToolExecutionCompleted(
                    tool_name=tc.name,
                    output=result.text_content,
                    is_error=result.is_error,
                    tool_use_id=tc.id,
                ), None
                tool_results_list.append(result)
            else:
                # 多个工具：并发执行
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
                for coro in asyncio.as_completed(
                    [_safe_run(i, tc) for i, tc in enumerate(tool_calls)]
                ):
                    idx, result, hook_ctxs = await coro
                    # 注入钩子 additionalContext
                    for ctx in hook_ctxs:
                        messages.append(ConversationMessage.from_user_text(_wrap_in_system_reminder(ctx)))
                    tool_results_list[idx] = result
                    yield ToolExecutionCompleted(
                        tool_name=tool_calls[idx].name,
                        output=result.text_content,
                        is_error=result.is_error,
                        tool_use_id=tool_calls[idx].id,
                    ), None
        except PermissionDenied as exc:
            from illusion.config.i18n import t
            # 为所有未完成的工具添加合成 tool_result，确保消息历史一致
            # （assistant 的 tool_use 必须有对应的 tool_result，否则 API 下一轮报错）
            # 单工具路径未预分配 tool_results_list，补齐至 tool_calls 长度
            tool_results_list.extend([None] * (len(tool_calls) - len(tool_results_list)))
            for i, tc in enumerate(tool_calls):
                if tool_results_list[i] is None:
                    tool_results_list[i] = ToolResultBlock(
                        tool_use_id=tc.id,
                        content=f"Permission denied for {tc.name}" if tc.name == exc.tool_name else f"Tool {tc.name} interrupted",
                        is_error=True,
                    )
            filtered_results: list[TextBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock | MediaBlock] = [r for r in tool_results_list if r is not None]
            messages.append(ConversationMessage(role="user", content=filtered_results))
            yield ErrorEvent(message=t("permission_denied_stopped", tool=exc.tool_name)), None
            return

        # 输出工具链完成事件
        yield ToolChainCompleted(
            results_summary=[
                {"name": tc.name, "is_error": result.is_error}
                for tc, result in zip(tool_calls, tool_results_list)
                if result is not None
            ]
        ), None

        # 将工具结果作为用户消息添加到历史记录
        all_results: list[TextBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock | MediaBlock] = [r for r in tool_results_list if r is not None]
        messages.append(ConversationMessage(role="user", content=all_results))

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
