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

from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

if TYPE_CHECKING:
    from illusion.services.checkpoint_store import CheckpointStore, RestoreResult

from illusion.api.client import SupportsStreamingMessages
from illusion.api.effort import EffortLevel
from illusion.api.usage import UsageSnapshot
from illusion.engine.cost_tracker import CostTracker
from illusion.engine.messages import ConversationMessage, ToolResultBlock
from illusion.engine.query import (
    AskUserPrompt,
    BackgroundAgentTracker,
    PermissionPrompt,
    PlanApprovalPrompt,
    QueryContext,
    run_query,
)
from illusion.engine.stream_events import StreamEvent
from illusion.hooks import HookEvent, HookExecutor
from illusion.permissions.checker import PermissionChecker
from illusion.services.compact import AutoCompactState, estimate_conversation_tokens
from illusion.services.file_history import (
    FileHistoryState,
    make_snapshot,
    track_edit,
)
from illusion.services.file_history import (
    load as _file_history_load,
)
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
        # 最后一次 API 调用的真实用量（含缓存分项），None 表示尚未调用或已失效
        self._last_api_usage: UsageSnapshot | None = None
        # last_api_usage 记录时的消息数快照，用于计算"自上次 API 调用以来新增消息"的增量
        self._last_api_usage_message_count: int = 0
        self._bg_agent_tracker = BackgroundAgentTracker()  # 后台代理追踪器
        self._compact_state = AutoCompactState()  # 自动压缩状态（跨会话持久）
        self._file_history: FileHistoryState | None = None  # 文件历史状态
        self._session_id: str = session_id or ""  # 会话 ID（用于文件历史目录）
        self._file_state_cache = FileStateCache()  # 文件状态缓存（用于读写去重）
        self._checkpoint_store: CheckpointStore | None = None  # 持久化存储

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
    def total_usage(self) -> UsageSnapshot:
        """返回跨所有轮次的总使用量。

        Returns:
            UsageSnapshot: 累积的使用量快照
        """
        return self._cost_tracker.total

    @property
    def system_prompt(self) -> str:
        """返回当前系统提示词。

        Returns:
            str: 当前 system prompt 文本
        """
        return self._system_prompt or ""

    @property
    def api_client(self) -> SupportsStreamingMessages:
        """返回当前 API 客户端（只读）。

        Returns:
            SupportsStreamingMessages: 当前 API 客户端实例
        """
        return self._api_client

    @property
    def model(self) -> str:
        """返回当前模型名（只读）。

        Returns:
            str: 当前模型名称
        """
        return self._model

    @property
    def last_api_usage(self) -> UsageSnapshot | None:
        """返回最后一次 API 调用的真实用量（含缓存分项）。

        压缩后会被清除，直到下一次 API 调用重新填充。

        Returns:
            UsageSnapshot | None: 最后一次调用的用量，None 表示无数据
        """
        return self._last_api_usage

    def invalidate_last_api_usage(self) -> None:
        """清除 last_api_usage 快照（压缩后调用）。

        压缩后压缩前的真实用量已不代表压缩后的上下文，清除后
        current_context_tokens() 回退到纯估算，直到下一次 API 调用
        提供新的真实值。
        """
        self._last_api_usage = None
        self._last_api_usage_message_count = 0

    def current_context_tokens(self) -> int:
        """当前上下文估算 = 最后一次 API 调用的真实 context_size + 新增消息估算。

        与 Claude Code 的 tokenCountWithEstimation() 同思路：真实 usage 为
        基准，新增消息用本地估算补齐，防止低估（低估会导致自动压缩触发
        过晚，API 调用失败）。

        Returns:
            int: 当前上下文占用 token 估算
        """
        if self._last_api_usage is not None:
            new_messages = self._messages[self._last_api_usage_message_count:]
            if new_messages:
                return (
                    self._last_api_usage.context_size
                    + estimate_conversation_tokens(new_messages)
                )
            return self._last_api_usage.context_size
        return estimate_conversation_tokens(self._messages)

    @property
    def tool_registry(self) -> ToolRegistry:
        """返回工具注册表（只读）。

        供侧问等外部服务复用 engine 的工具集，无需重复构建。
        """
        return self._tool_registry

    @property
    def permission_checker(self) -> PermissionChecker:
        """返回权限检查器（只读）。

        供侧问等外部服务复用 engine 的权限配置。
        """
        return self._permission_checker

    @property
    def cwd(self) -> Path:
        """返回当前工作目录（只读）。"""
        return self._cwd

    @property
    def tool_metadata(self) -> dict[str, object]:
        """返回工具元数据（只读）。"""
        return self._tool_metadata

    def clear(self) -> None:
        """清除内存中的对话历史。

        同时重置成本跟踪器、last_api_usage 和文件状态缓存。
        注意：不清除 _checkpoint_store 和 _session_id，由 full_reset 处理。
        """
        self._messages.clear()
        self._cost_tracker = CostTracker()
        self._last_api_usage = None
        self._last_api_usage_message_count = 0
        self._file_state_cache.clear()

    def set_checkpoint_store(self, store: CheckpointStore | None) -> None:
        """设置或清除 CheckpointStore。

        Args:
            store: CheckpointStore 实例或 None
        """
        self._checkpoint_store = store

    def set_session_id(self, session_id: str) -> None:
        """更新引擎内部的 session_id（用于 /new、/resume 后同步）。

        同时同步已加载的 file_history.session_id，避免 file_history.json
        写入与 session_dir 不匹配的孤立目录。

        Args:
            session_id: 新的会话 ID
        """
        self._session_id = session_id
        if self._file_history is not None and self._file_history.session_id != session_id:
            self._file_history.session_id = session_id
            # 若旧 session_id 下已落盘，则按新 session_id 再保存一次，
            # 确保后续 track_edit/rewind_to 写入正确目录
            from illusion.services.file_history import save as _fh_save
            _fh_save(self._file_history)

    def full_reset(self) -> None:
        """完全重置引擎状态（用于 /new）。

        清空消息历史、cost_tracker、last_api_usage、file_history、
        file_state_cache、session_id 和 checkpoint_store。
        """
        self._messages.clear()
        self._cost_tracker = CostTracker()
        self._last_api_usage = None
        self._last_api_usage_message_count = 0
        self._file_history = None
        self._file_state_cache.clear()
        self._session_id = ""
        self._checkpoint_store = None

    def apply_restore(self, result: RestoreResult) -> None:
        """从 CheckpointStore.restore() 结果恢复所有状态。

        system_prompt 不从持久化恢复——下一轮 handle_line 会通过
        build_runtime_system_prompt 重新构建。
        last_api_usage 从 checkpoint 中的单次分项恢复（若有），
        使 rewind/resume 后 StatusBar / context 显示立即恢复。

        Args:
            result: restore 结果
        """
        self._messages = list(result.messages)
        self._cost_tracker.apply_restore(result)
        # 恢复最后一次 API 调用的单次用量（含缓存分项），
        # 使 rewind/resume 后 StatusBar / context 显示立即恢复
        # （checkpoint 中无该数据时回退到 None → 纯估算）
        self._last_api_usage = result.last_usage
        self._last_api_usage_message_count = result.last_usage_message_count

    def load_file_history(self, checkpoint_count: int | None = None) -> None:
        """显式加载文件历史状态（用于 /resume 后）。

        在 apply_restore 之后调用，确保 /rewind 前状态已就绪。
        若磁盘上无 file_history.json 则保持现有状态不变。

        Args:
            checkpoint_count: 当前 CheckpointStore.next_checkpoint_id，
                用于崩溃恢复对齐。None 时不做对齐。
        """
        if not self._session_id:
            return
        loaded = _file_history_load(
            str(self._cwd), self._session_id, checkpoint_count=checkpoint_count
        )
        if loaded is not None:
            self._file_history = loaded

    @property
    def checkpoint_store(self) -> CheckpointStore | None:
        """返回当前 CheckpointStore。"""
        return self._checkpoint_store

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

    def on_before_tool_execute(self, tool_name: str, tool_input: dict[str, Any]) -> None:
        """工具执行前回调：备份即将被修改的文件（copy-on-write）。

        供主引擎和子 agent 共用：子 agent 通过 QueryContext 继承此回调，
        其文件修改也会备份到主 engine 的 file_history，确保 rewind 能覆盖
        子 agent 的修改。

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
        """
        if self._file_history is None:
            return
        # 跳过只读工具（如 grep、glob），它们不会修改文件
        tool = self._tool_registry.get(tool_name)
        if tool is not None:
            try:
                parsed_input = tool.input_model.model_validate(tool_input)
                if tool.is_read_only(parsed_input):
                    return
            except ValidationError:
                pass
        for fpath in self._extract_file_paths(tool_name, tool_input):
            track_edit(self._file_history, fpath)

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
        # system_prompt 不再持久化：system_prompt 不含 tools 描述，
        # hash 无法完整代表系统级开销变化。改为每轮反推自校正
        # （update_from_usage 无条件覆盖），resume 后用持久化的 overhead
        # 值显示，第一轮 API 调用后用实测值覆盖。
        # append checkpoint 到 JSONL（替代旧 push_checkpoint）
        checkpoint_id = 0
        if self._checkpoint_store is not None:
            checkpoint_id = await self._checkpoint_store.append_checkpoint()
        # 初始化文件历史状态（load 优先，无则新建）
        # 要求 self._session_id 已由 runtime 层设置（/new、/resume、首启均会同步）。
        # 若仍为空，说明 runtime 未正确同步，跳过 file_history 创建——
        # file_history.json 写入随机 id 会导致路径与 session_dir 不匹配，
        # 重启后 resume 无法加载，rewind 失效。
        if self._file_history is None and self._session_id:
            loaded = _file_history_load(str(self._cwd), self._session_id)
            if loaded is not None:
                self._file_history = loaded
            else:
                self._file_history = FileHistoryState(
                    session_id=self._session_id,
                    cwd=str(self._cwd),
                )

        # 将用户文本转换为消息并添加到历史记录
        self._messages.append(ConversationMessage.from_user_text(prompt))
        # 持久化 user message
        if self._checkpoint_store is not None:
            await self._checkpoint_store.append_message(self._messages[-1])

        # 执行 UserPromptSubmit 钩子
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
        # 仅当 file_history 已初始化（session_id 可用）时才创建快照
        if self._file_history is not None:
            make_snapshot(self._file_history, str(len(self._messages)), checkpoint_id)

        # 文件历史回调：工具执行前备份文件（使用方法，供子 agent 继承复用）
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
            last_api_usage=self._last_api_usage,
            last_api_usage_message_count=self._last_api_usage_message_count,
            on_before_tool_execute=self.on_before_tool_execute,
            file_state_cache=self._file_state_cache,
        )
        # 记录循环前的消息数量，用于循环结束后持久化新增消息
        # run_query 内部会直接 append assistant/tool 消息到 self._messages，
        # 这些消息必须持久化，否则 resume 后只看到用户消息，丢失 LLM 回复
        messages_before = len(self._messages)
        try:
            async for event, usage in run_query(context, self._messages):
                if usage is not None:
                    self._cost_tracker.add(usage)  # 累加使用量
                    # 记录最后一次 API 调用的真实用量（含缓存分项）及消息数快照
                    self._last_api_usage = usage
                    self._last_api_usage_message_count = len(self._messages)
                    # 持久化累积 usage + 最后一次调用的单次分项
                    # （单次分项用于 rewind/resume 后恢复 StatusBar 显示）
                    if self._checkpoint_store is not None:
                        await self._checkpoint_store.append_usage(
                            input_tokens=self._cost_tracker.total.input_tokens,
                            output_tokens=self._cost_tracker.total.output_tokens,
                            cache_read_input_tokens=self._cost_tracker.total.cache_read_input_tokens,
                            cache_creation_input_tokens=self._cost_tracker.total.cache_creation_input_tokens,
                            last_usage=usage,
                            last_message_count=len(self._messages),
                        )
                yield event
        finally:
            # 同步压缩后的消息列表（full compact 后 messages 指向新列表）
            if context.final_messages is not None and context.final_messages is not self._messages:
                self._messages = context.final_messages
            if self._checkpoint_store is not None:
                if context.compacted:
                    # run_query 内发生过压缩：重建 checkpoint，
                    # 否则 resume/rewind 会恢复到压缩前的完整历史
                    await self._checkpoint_store.rebuild_after_compact(
                        self._messages,
                        usage_input=self._cost_tracker.total.input_tokens,
                        usage_output=self._cost_tracker.total.output_tokens,
                        usage_cache_read=self._cost_tracker.total.cache_read_input_tokens,
                        usage_cache_creation=self._cost_tracker.total.cache_creation_input_tokens,
                    )
                else:
                    # 持久化 run_query 期间新增的所有消息（assistant 回复、tool 结果、
                    # hook 注入的 user 消息等）。使用 finally 确保即使异常/中断也能
                    # 保存已生成的消息，避免 resume 后对话历史缺失。
                    for msg in self._messages[messages_before:]:
                        await self._checkpoint_store.append_message(msg)
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
            last_api_usage=self._last_api_usage,
            last_api_usage_message_count=self._last_api_usage_message_count,
            on_before_tool_execute=self.on_before_tool_execute,
            file_state_cache=self._file_state_cache,
        )
        # 记录循环前的消息数量，用于循环结束后持久化新增消息
        # continue_pending 不 append checkpoint，但 run_query 内部仍会
        # append assistant/tool 消息，需要持久化以支持 resume
        messages_before = len(self._messages)
        try:
            async for event, usage in run_query(context, self._messages):
                if usage is not None:
                    self._cost_tracker.add(usage)  # 累加使用量
                    # 记录最后一次 API 调用的真实用量（含缓存分项）及消息数快照
                    self._last_api_usage = usage
                    self._last_api_usage_message_count = len(self._messages)
                    # 持久化累积 usage + 最后一次调用的单次分项
                    # （continue_pending 不 append checkpoint）
                    if self._checkpoint_store is not None:
                        await self._checkpoint_store.append_usage(
                            input_tokens=self._cost_tracker.total.input_tokens,
                            output_tokens=self._cost_tracker.total.output_tokens,
                            cache_read_input_tokens=self._cost_tracker.total.cache_read_input_tokens,
                            cache_creation_input_tokens=self._cost_tracker.total.cache_creation_input_tokens,
                            last_usage=usage,
                            last_message_count=len(self._messages),
                        )
                yield event
        finally:
            # 同步压缩后的消息列表（full compact 后 messages 指向新列表）
            if context.final_messages is not None and context.final_messages is not self._messages:
                self._messages = context.final_messages
            if self._checkpoint_store is not None:
                if context.compacted:
                    # 与 submit_message 一致：压缩后重建 checkpoint
                    await self._checkpoint_store.rebuild_after_compact(
                        self._messages,
                        usage_input=self._cost_tracker.total.input_tokens,
                        usage_output=self._cost_tracker.total.output_tokens,
                        usage_cache_read=self._cost_tracker.total.cache_read_input_tokens,
                        usage_cache_creation=self._cost_tracker.total.cache_creation_input_tokens,
                    )
                else:
                    # 持久化 run_query 期间新增的所有消息（与 submit_message 一致）
                    for msg in self._messages[messages_before:]:
                        await self._checkpoint_store.append_message(msg)
        # 同步工具导致的 CWD 变更（如 enter/exit_worktree）
        if context.cwd != self._cwd:
            self._cwd = context.cwd
