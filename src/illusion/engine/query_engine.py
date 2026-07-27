"""高级对话引擎。

本模块提供高级对话引擎，管理对话历史和工具感知的模型循环。

主要功能：
    - 管理对话历史
    - 执行用户消息提交
    - 支持待续工具调用继续
    - 跟踪令牌使用成本

主要类：
    - QueryEngine: 对话引擎主类

使用示例：
    >>> from illusion.engine import QueryEngine
    >>> engine = QueryEngine(
    ...     api_client=client,
    ...     tool_registry=registry,
    ...     permission_checker=checker,
    ...     cwd=".",
    ...     model="claude-3-opus",
    ...     system_prompt="你是一个助手"
    ... )
    >>> async for event in engine.submit_message("你好"):
    ...     print(event)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any,  AsyncIterator

from illusion.api.client import SupportsStreamingMessages
from illusion.api.usage import UsageSnapshot
from illusion.api.effort import EffortLevel
from illusion.engine.cost_tracker import CostTracker
from illusion.engine.messages import ConversationMessage, ToolResultBlock
from illusion.engine.query import AskUserPrompt, BackgroundAgentTracker, PermissionPrompt, PlanApprovalPrompt, QueryContext, run_query
from illusion.engine.stream_events import StreamEvent
from illusion.hooks import HookEvent, HookExecutor
from illusion.permissions.checker import PermissionChecker
from illusion.services.compact import AutoCompactState
from illusion.services.file_history import FileHistoryState, track_edit, make_snapshot
from illusion.tools.base import ToolRegistry
from illusion.utils.file_state_cache import FileStateCache


class QueryEngine:
    """拥有对话历史和工具感知模型循环的高级引擎。

    管理整个对话生命周期，包括消息提交、工具执行、成本跟踪等。

    Attributes:
        messages: 当前对话历史（只读）
        max_turns: 每个用户输入的最大智能体轮次数
        total_usage: 跨所有轮次的总使用量

    使用示例：
        >>> engine = QueryEngine(
        ...     api_client=client,
        ...     tool_registry=registry,
        ...     permission_checker=checker,
        ...     cwd=".",
        ...     model="claude-3-opus",
        ...     system_prompt="你是一个助手"
        ... )
    """

    def __init__(
        self,
        *,
        api_client: SupportsStreamingMessages,
        tool_registry: ToolRegistry,
        permission_checker: PermissionChecker,
        cwd: str | Path,
        model: str,
        system_prompt: str,
        max_tokens: int = 4096,
        max_turns: int | None = 8,
        permission_prompt: PermissionPrompt | None = None,
        ask_user_prompt: AskUserPrompt | None = None,
        plan_approval_prompt: PlanApprovalPrompt | None = None,
        hook_executor: HookExecutor | None = None,
        tool_metadata: dict[str, object] | None = None,
        effort: EffortLevel | None = None,
        session_id: str = "",
    ) -> None:
        self._api_client = api_client  # API客户端
        self._tool_registry = tool_registry  # 工具注册表
        self._permission_checker = permission_checker  # 权限检查器
        self._cwd = Path(cwd).resolve()  # 当前工作目录
        self._model = model  # 模型名称
        self._system_prompt = system_prompt  # 系统提示词
        self._max_tokens = max_tokens  # 最大令牌数
        self._max_turns = max_turns  # 最大轮次
        self._permission_prompt = permission_prompt  # 权限提示回调
        self._ask_user_prompt = ask_user_prompt  # 用户询问回调
        self._plan_approval_prompt = plan_approval_prompt  # 计划审批回调
        self._hook_executor = hook_executor  # 钩子执行器
        self._tool_metadata = tool_metadata or {}  # 工具元数据
        self._effort = effort  # effort 级别
        self._messages: list[ConversationMessage] = []  # 对话消息历史
        self._cost_tracker = CostTracker()  # 成本跟踪器
        self._bg_agent_tracker = BackgroundAgentTracker()  # 后台代理追踪器
        self._compact_state = AutoCompactState()  # 自动压缩状态（跨会话持久）
        self._file_history: FileHistoryState | None = None  # 文件历史状态
        self._session_id: str = session_id or ""  # 会话 ID（用于文件历史目录）
        self._file_state_cache = FileStateCache()  # 文件状态缓存（用于读写去重）

    @property
    def effort(self) -> EffortLevel | None:
        """返回当前的 effort 级别。

        Returns:
            EffortLevel | None: 当前的 effort 级别
        """
        return self._effort

    @effort.setter
    def effort(self, value: EffortLevel | None) -> None:
        """设置 effort 级别。

        Args:
            value: 新的 effort 级别
        """
        self._effort = value

    @property
    def max_tokens(self) -> int:
        """返回当前的最大令牌数。

        Returns:
            int: 最大令牌数
        """
        return self._max_tokens

    @max_tokens.setter
    def max_tokens(self, value: int) -> None:
        """设置最大令牌数。

        Args:
            value: 新的最大令牌数
        """
        self._max_tokens = value

    @property
    def messages(self) -> list[ConversationMessage]:
        """返回当前对话历史。

        Returns:
            list[ConversationMessage]: 消息列表的副本
        """
        return list(self._messages)

    @property
    def max_turns(self) -> int | None:
        """返回每个用户输入的最大智能体轮次数（如果有上限）。

        Returns:
            int | None: 最大轮次数或None（无限制）
        """
        return self._max_turns

    @property
    def total_usage(self) -> "UsageSnapshot":
        """返回跨所有轮次的总使用量。

        Returns:
            UsageSnapshot: 累积的使用量快照
        """
        return self._cost_tracker.total

    def clear(self) -> None:
        """清除内存中的对话历史。

        同时重置成本跟踪器和文件状态缓存。
        """
        self._messages.clear()
        self._cost_tracker = CostTracker()
        self._file_state_cache.clear()

    async def aclose(self) -> None:
        """关闭查询引擎，cancel 所有未完成后台 task。

        调用 BackgroundAgentTracker.shutdown() 取消 pending task，
        并等待最多 5 秒让 task 完成清理，避免 engine 退出后
        wait_for_completion 永久阻塞。
        """
        self._bg_agent_tracker.shutdown()
        await self._bg_agent_tracker.wait_for_completion(timeout=5.0)

    def set_system_prompt(self, prompt: str) -> None:
        """更新未来轮次的活跃系统提示词。

        Args:
            prompt: 新的系统提示词
        """
        self._system_prompt = prompt

    def set_model(self, model: str) -> None:
        """更新未来轮次的活跃模型。

        Args:
            model: 新的模型名称
        """
        self._model = model

    def set_api_client(self, api_client: SupportsStreamingMessages) -> None:
        """更新未来轮次的活跃API客户端。

        Args:
            api_client: 新的API客户端
        """
        self._api_client = api_client

    def set_max_turns(self, max_turns: int | None) -> None:
        """更新每个用户输入的最大智能体轮次数。

        Args:
            max_turns: 最大轮次数，None表示无限制
        """
        self._max_turns = None if max_turns is None else max(1, int(max_turns))

    def set_permission_checker(self, checker: PermissionChecker) -> None:
        """更新未来轮次的活跃权限检查器。

        Args:
            checker: 新的权限检查器
        """
        self._permission_checker = checker

    def load_messages(self, messages: list[ConversationMessage]) -> None:
        """替换内存中的对话历史。

        Args:
            messages: 新的消息列表
        """
        self._messages = list(messages)

    @property
    def file_history(self) -> FileHistoryState | None:
        """返回文件历史状态。"""
        return self._file_history

    def _extract_file_paths(self, tool_name: str, tool_input: dict[str, Any]) -> list[str]:
        """从工具输入中提取文件路径。"""
        path_keys = ("path", "file_path", "notebook_path")
        paths = []
        for key in path_keys:
            if key in tool_input and isinstance(tool_input[key], str):
                paths.append(tool_input[key])
        return paths

    def has_pending_continuation(self) -> bool:
        """当对话以等待后续模型轮次的工具结果结束时返回True。

        用于检查是否有待续的工具调用需要继续执行。

        Returns:
            bool: 是否有待续的继续
        """
        if not self._messages:
            return False
        last = self._messages[-1]
        if last.role != "user":
            return False
        if not any(isinstance(block, ToolResultBlock) for block in last.content):
            return False
        for msg in reversed(self._messages[:-1]):
            if msg.role != "assistant":
                continue
            return bool(msg.tool_uses)
        return False

    async def submit_message(self, prompt: str) -> AsyncIterator[StreamEvent]:
        """追加用户消息并执行查询循环。

        Args:
            prompt: 用户输入的提示词

        Yields:
            StreamEvent: 流式事件

        使用示例：
            >>> async for event in engine.submit_message("你好"):
            ...     print(event)
        """
        # 初始化文件历史状态（如尚未初始化）
        if self._file_history is None:
            self._file_history = FileHistoryState(
                session_id=self._session_id or __import__('uuid').uuid4().hex[:12],
                cwd=str(self._cwd),
            )

        # 将用户文本转换为消息并添加到历史记录
        self._messages.append(ConversationMessage.from_user_text(prompt))

        # 执行 UserPromptSubmit 钩子（对齐 Claude Code）
        if self._hook_executor is not None:
            ups_result = await self._hook_executor.execute(
                HookEvent.USER_PROMPT_SUBMIT,
                {"prompt": prompt},
            )
            # 阻止处理
            if ups_result.blocked:
                from illusion.hooks.utils import wrap_in_system_reminder
                error_msg = ups_result.reason or "UserPromptSubmit hook blocked"
                self._messages.append(ConversationMessage.from_user_text(
                    wrap_in_system_reminder(f"Hook blocked: {error_msg}")
                ))
                return
            # preventContinuation
            if ups_result.prevent_continuation:
                return
            # 注入 additionalContext
            for ctx in ups_result.additional_contexts:
                if ctx:
                    from illusion.hooks.utils import wrap_in_system_reminder
                    self._messages.append(ConversationMessage.from_user_text(
                        wrap_in_system_reminder(ctx)
                    ))

        # 为这条用户消息创建文件历史快照（用消息列表长度作为 ID）
        make_snapshot(self._file_history, str(len(self._messages)))

        # 文件历史回调：工具执行前备份文件
        def _on_before_tool_execute(tool_name: str, tool_input: dict[str, Any]) -> None:
            if self._file_history is None:
                return
            # 跳过只读工具（如 grep、glob），它们不会修改文件
            tool = self._tool_registry.get(tool_name)
            if tool is not None:
                try:
                    parsed_input = tool.input_model.model_validate(tool_input)
                    if tool.is_read_only(parsed_input):
                        return
                except Exception:
                    pass
            for fpath in self._extract_file_paths(tool_name, tool_input):
                track_edit(self._file_history, fpath)

        context = QueryContext(
            api_client=self._api_client,
            tool_registry=self._tool_registry,
            permission_checker=self._permission_checker,
            cwd=self._cwd,
            model=self._model,
            system_prompt=self._system_prompt,
            max_tokens=self._max_tokens,
            max_turns=self._max_turns,
            permission_prompt=self._permission_prompt,
            ask_user_prompt=self._ask_user_prompt,
            plan_approval_prompt=self._plan_approval_prompt,
            hook_executor=self._hook_executor,
            tool_metadata=self._tool_metadata,
            effort=self._effort,
            bg_agent_tracker=self._bg_agent_tracker,
            # idle 超时阈值：后台 agent 持续有活动（工具调用、文本生成）时
            # 主循环保持 busy；仅当 300s 无任何活动才退出 busy（agent 仍存活，
            # 下轮 handle_line 续接）。与前台 IDLE_TIMEOUT 一致。
            bg_agent_wait_timeout=300.0,
            compact_state=self._compact_state,
            on_before_tool_execute=_on_before_tool_execute,
            file_state_cache=self._file_state_cache,
        )
        async for event, usage in run_query(context, self._messages):
            if usage is not None:
                self._cost_tracker.add(usage)  # 累加使用量
            yield event
        # 同步工具导致的 CWD 变更（如 enter/exit_worktree）
        if context.cwd != self._cwd:
            self._cwd = context.cwd

    async def continue_pending(self, *, max_turns: int | None = None) -> AsyncIterator[StreamEvent]:
        """继续被中断的工具循环，而不追加新的用户消息。

        用于恢复之前因工具执行而中断的对话。

        Args:
            max_turns: 最大轮次数（可选，默认使用引擎设置）

        Yields:
            StreamEvent: 流式事件
        """
        context = QueryContext(
            api_client=self._api_client,
            tool_registry=self._tool_registry,
            permission_checker=self._permission_checker,
            cwd=self._cwd,
            model=self._model,
            system_prompt=self._system_prompt,
            max_tokens=self._max_tokens,
            max_turns=max_turns if max_turns is not None else self._max_turns,
            permission_prompt=self._permission_prompt,
            ask_user_prompt=self._ask_user_prompt,
            plan_approval_prompt=self._plan_approval_prompt,
            hook_executor=self._hook_executor,
            tool_metadata=self._tool_metadata,
            effort=self._effort,
            bg_agent_tracker=self._bg_agent_tracker,
            # idle 超时阈值（与 build_query_context 一致，详见上文说明）
            bg_agent_wait_timeout=300.0,
            compact_state=self._compact_state,
            file_state_cache=self._file_state_cache,
        )
        async for event, usage in run_query(context, self._messages):
            if usage is not None:
                self._cost_tracker.add(usage)  # 累加使用量
            yield event
        # 同步工具导致的 CWD 变更（如 enter/exit_worktree）
        if context.cwd != self._cwd:
            self._cwd = context.cwd
