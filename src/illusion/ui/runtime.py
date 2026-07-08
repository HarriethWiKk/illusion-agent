"""
Runtime 运行时模块
================

本模块实现无 UI 和 Textual UI 共享的运行时程序集。

主要功能：
    - 运行时数据 bundle 管理
    - API 客户端初始化和配置
    - 工具注册和权限检查
    - 会话状态管理
    - 命令处理和执行
    - 会话快照保存

类说明：
    - RuntimeBundle: 共享运行时数据bundle
    - build_runtime: 构建运行时
    - start_runtime: 启动运行时（执行会话开始钩子）
    - close_runtime: 关闭运行时并清理资源
    - handle_line: 处理用户输入行
    - sync_app_state: 同步应用状态

使用示例：
    >>> from illusion.ui.runtime import build_runtime, handle_line, start_runtime, close_runtime
    >>> 
    >>> # 构建运行时
    >>> bundle = await build_runtime(model="claude-sonnet-4-20250514")
    >>> await start_runtime(bundle)
    >>> 
    >>> # 处理输入行
    >>> await handle_line(
    ...     bundle,
    ...     "帮我写一个 hello world 程序",
    ...     print_system=print_system,
    ...     render_event=render_event,
    ...     clear_output=clear_output,
    ... )
    >>> 
    >>> # 关闭运行时
    >>> await close_runtime(bundle)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

from illusion.api.client import AnthropicApiClient, SupportsStreamingMessages
from illusion.api.effort import EffortMapper
from illusion.api.openai_client import OpenAICompatibleClient
from illusion.api.auth_status import auth_status
from illusion.bridge import get_bridge_manager
from illusion.commands import CommandContext, CommandResult, create_default_command_registry
from illusion.commands.registry import CommandRegistry
from illusion.config import load_settings
from illusion.config.settings import Settings
from illusion.engine import QueryEngine
from illusion.engine.messages import ConversationMessage, ToolResultBlock, ToolUseBlock
from illusion.engine.query import MaxTurnsExceeded
from illusion.engine.stream_events import StreamEvent
from illusion.hooks import HookEvent, HookExecutionContext, HookExecutor
from illusion.hooks.loader import load_hook_registry
from illusion.hooks.types import AggregatedHookResult
from illusion.mcp.client import McpClientManager
from illusion.mcp.config import load_mcp_server_configs
from illusion.permissions import PermissionChecker
from illusion.plugins.loader import load_plugins
from illusion.plugins.types import LoadedPlugin
from illusion.prompts import build_runtime_system_prompt
from illusion.state import AppState, AppStateStore
from illusion.services.session_storage import save_session_snapshot
from illusion.tools import ToolRegistry, create_default_tool_registry
from illusion.tasks.types import TaskRecord

# 类型别名定义
PermissionPrompt = Callable[[str, str], Awaitable[bool]]  # 权限确认回调
AskUserPrompt = Callable[[str, object], Awaitable[str]]  # 用户问答回调
PlanApprovalPrompt = Callable[[str], Awaitable[tuple[bool, str]]]  # 计划审批回调
SystemPrinter = Callable[[str], Awaitable[None]]  # 系统消息打印回调
StreamRenderer = Callable[[StreamEvent], Awaitable[None]]  # 流式事件渲染回调
ClearHandler = Callable[[], Awaitable[None]]  # 清空输出回调
TranscriptItemSender = Callable[[dict[str, Any]], Awaitable[None]]  # 发送 transcript_item 的回调
CommandResultEmitter = Callable[[str, str], Awaitable[None]]  # 指令结果发射回调（message, type）
ReplaceTranscriptItems = Callable[[list[dict[str, Any]]], Awaitable[None]]  # 替换转录项列表的回调


@dataclass
class RuntimeBundle:
    """共享运行时数据bundle。

    用于存储一次交互式会话的所有运行时对象。
    包括 API 客户端、工具注册器、引擎、状态管理等。

    Attributes:
        api_client: 流式 API 客户端实例
        cwd: 当前工作目录
        mcp_manager: MCP 客户端管理器
        tool_registry: 工具注册器
        app_state: 应用状态存储
        hook_executor: 钩子执行器
        engine: 查询引擎
        commands: 命令注册表
        external_api_client: 是否使用外部 API 客户端
        session_id: 会话 ID
        settings_overrides: 设置覆盖字典
    """

    api_client: SupportsStreamingMessages
    cwd: str
    mcp_manager: McpClientManager
    tool_registry: ToolRegistry
    app_state: AppStateStore
    hook_executor: HookExecutor
    engine: QueryEngine
    commands: CommandRegistry
    external_api_client: bool
    session_id: str = ""
    settings_overrides: dict[str, Any] = field(default_factory=dict[str, Any])
    # 钩子注入的 additionalContext（在 start_runtime 中设置，每次 handle_line 重建系统提示词后追加）
    hook_additional_contexts: list[str] = field(default_factory=list[Any])
    # 渠道感知提示词（PC 终端或渠道端注入），handle_line 重建系统提示词时复用
    channel_hint: str | None = None

    def current_settings(self) -> Settings:
        """返回会话的有效设置。

        大多数设置持久化到磁盘（~/.illusion/settings.json），
        但 CLI 选项如 --model/--api-format 在进程生命周期内保持有效。
        没有此覆盖，发送任何斜杠命令（如 /fast）会从磁盘刷新 UI 状态，
        并将 model/provider " snap back" 到配置文件中的值。
        """
        return load_settings().merge_cli_overrides(**self.settings_overrides)

    def current_plugins(self) -> list[LoadedPlugin]:
        """返回当前工作树的可见插件。"""
        return load_plugins(self.current_settings(), self.cwd)

    def hook_summary(self) -> str:
        """返回当前钩子摘要。"""
        return load_hook_registry(self.current_settings(), self.current_plugins()).summary()

    def plugin_summary(self) -> str:
        """返回当前插件摘要。"""
        plugins = self.current_plugins()
        if not plugins:
            return "No plugins discovered."
        lines = ["Plugins:"]
        for plugin in plugins:
            state = "enabled" if plugin.enabled else "disabled"
            lines.append(f"- {plugin.manifest.name} [{state}] {plugin.manifest.description}")
        return "\n".join(lines)

    def mcp_summary(self) -> str:
        """返回当前 MCP 摘要。"""
        statuses = self.mcp_manager.list_statuses()
        if not statuses:
            return "No MCP servers configured."
        lines = ["MCP servers:"]
        for status in statuses:
            suffix = f" - {status.detail}" if status.detail else ""
            lines.append(f"- {status.name}: {status.state}{suffix}")
            if status.tools:
                lines.append(f"  tools: {', '.join(tool.name for tool in status.tools)}")
            if status.resources:
                lines.append(f"  resources: {', '.join(resource.uri for resource in status.resources)}")
        return "\n".join(lines)


def _on_task_complete(
    task_id: str,
    task: "TaskRecord",
    tracker: "BackgroundAgentTracker",
) -> None:
    """后台任务完成后，通过 bg_agent_tracker 注入通知 XML。

    支持 agent 类任务（local_agent/remote_agent/in_process_teammate）
    和 bash/powershell 后台命令（local_bash）。其他类型忽略。

    Args:
        task_id: 任务 ID
        task: 任务记录
        tracker: 后台代理追踪器，用于注入 <task-notification> XML
    """
    from illusion.swarm.agent_executor import TaskNotification, format_task_notification

    if task.type in {"local_agent", "remote_agent", "in_process_teammate"}:
        agent_id = task.metadata.get("agent_id", task_id)
        # 构建通知 XML（子进程不返回 AgentResult，使用 task 描述作为 summary）
        notification = TaskNotification(
            task_id=agent_id,
            status=task.status,
            summary=task.description or f"Agent {agent_id} {task.status}",
            result=None,
            usage=None,
        )
        notification_xml = format_task_notification(notification)
        tracker.notify_completed(agent_id, notification_xml)
    elif task.type == "local_bash":
        # 后台 Bash/PowerShell 命令完成后通知 LLM，与工具提示词承诺一致
        summary = f'Background command "{task.description}" {task.status}'
        if task.return_code is not None:
            summary += f" (exit code {task.return_code})"
        notification = TaskNotification(
            task_id=task_id,
            status=task.status,
            summary=summary,
            result=None,
            usage=None,
        )
        notification_xml = format_task_notification(notification)
        tracker.notify_completed(task_id, notification_xml)


def _build_system_prompt_with_append(
    settings: Any,
    *,
    cwd: str,
    latest_user_prompt: str | None,
    channel_hint: str | None,
    append_system_prompt: str | None,
) -> str:
    """构建系统提示词，并可选追加用户指定内容。

    Args:
        settings: 配置实例
        cwd: 工作目录
        latest_user_prompt: 最新的用户提示词
        channel_hint: 渠道感知提示词
        append_system_prompt: 追加到系统提示词末尾的内容

    Returns:
        str: 完整的系统提示词
    """
    _base_prompt = build_runtime_system_prompt(
        settings,
        cwd=cwd,
        latest_user_prompt=latest_user_prompt,
        channel_hint=channel_hint,
    )
    if append_system_prompt:
        _base_prompt = _base_prompt + "\n\n" + append_system_prompt
    return _base_prompt


async def build_runtime(
    *,
    prompt: str | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    api_key: str | None = None,
    api_format: str | None = None,
    api_client: SupportsStreamingMessages | None = None,
    permission_prompt: PermissionPrompt | None = None,
    ask_user_prompt: AskUserPrompt | None = None,
    plan_approval_prompt: PlanApprovalPrompt | None = None,
    restore_messages: list[dict[str, Any]] | None = None,
    restore_session_id: str | None = None,
    effort: str | None = None,
    is_interactive: bool = True,
    channel_hint: str | None = None,
    channel_tools: list[Any] | None = None,
    settings_file: str | None = None,
    permission_mode: str | None = None,
    append_system_prompt: str | None = None,
    verbose: bool = False,
    debug: bool = False,
    bare: bool = False,
) -> RuntimeBundle:
    """构建 IllusionCode 会话的共享运行时。

    初始化所有运行时对象，包括 API 客户端、插件、工具注册器、引擎等。

    Args:
        prompt: 初始用户提示词
        model: 使用的模型名称
        max_turns: 最大对话轮次
        base_url: API 基础 URL
        system_prompt: 系统提示词
        api_key: API 密钥
        api_format: API 格式（openai/anthropic）
        api_client: 流式 API 客户端实例
        permission_prompt: 权限确认回调函数
        ask_user_prompt: 用户问答回调函数
        restore_messages: 恢复的会话消息列表
        effort: 推理强度级别（low/medium/high/xhigh/max）
        is_interactive: 是否为交互模式（默认True）。非交互模式下会加载StructuredOutputTool。
        verbose: 启用 INFO 级别日志（CLI --verbose）
        debug: 启用 DEBUG 级别日志（CLI --debug）
        bare: 纯净模式，跳过 plugins/MCP auto-discovery（CLI --bare）

    Returns:
        RuntimeBundle: 运行时数据 bundle
    """
    # 配置日志级别（CLI --verbose / --debug）
    import logging
    if debug:
        logging.getLogger("illusion").setLevel(logging.DEBUG)
    elif verbose:
        logging.getLogger("illusion").setLevel(logging.INFO)
    # 构建设置覆盖字典
    settings_overrides: dict[str, Any] = {
        "model": model,
        "max_turns": max_turns,
        "base_url": base_url,
        "system_prompt": system_prompt,
        "api_key": api_key,
        "api_format": api_format,
        "effort": effort,
    }
    settings = load_settings(
        config_path=Path(settings_file) if settings_file else None
    ).merge_cli_overrides(**settings_overrides)
    # 覆盖权限模式（CLI --permission-mode / --dangerously-skip-permissions）
    if permission_mode is not None:
        from illusion.permissions.modes import PermissionMode
        try:
            settings = settings.model_copy(update={
                "permission": settings.permission.model_copy(
                    update={"mode": PermissionMode(permission_mode)}
                )
            })
        except ValueError:
            import logging
            logging.getLogger(__name__).warning(
                f"Invalid permission_mode: {permission_mode}, ignoring"
            )
    session_id = restore_session_id or uuid4().hex[:12]
    # 获取当前工作目录
    cwd = str(Path.cwd())
    # 加载插件（--bare 模式跳过）
    if not bare:
        plugins = load_plugins(settings, cwd)
    else:
        plugins = []
    # 解析 API 客户端
    resolved_api_client: SupportsStreamingMessages
    _web_auth_missing = False
    try:
        if api_client:
            resolved_api_client = api_client
        elif settings.api_format == "copilot":
            from illusion.auth.copilot import CopilotAuth, copilot_extra_headers
            _copilot = CopilotAuth()
            _copilot_token = _copilot.get_valid_token()
            resolved_api_client = OpenAICompatibleClient(  # type: ignore[assignment]
                api_key=_copilot_token,
                base_url=settings.base_url or "https://api.githubcopilot.com",
                extra_headers=copilot_extra_headers(),
            )
        elif settings.api_format == "codex":
            from illusion.auth.codex_oauth import CodexOAuth
            from illusion.api.codex_client import CodexApiClient
            resolved_api_client = CodexApiClient(  # type: ignore[assignment]
                auth_token_resolver=CodexOAuth().get_valid_token,
                base_url=settings.base_url,
            )
        elif settings.api_format == "anthropic":
            resolved_api_client = AnthropicApiClient(  # type: ignore[assignment]
                api_key=settings.resolve_api_key(),
                base_url=settings.base_url,
            )
        else:  # "openai" 及其他 OpenAI 兼容格式
            resolved_api_client = OpenAICompatibleClient(  # type: ignore[assignment]
                api_key=settings.resolve_api_key(),
                base_url=settings.base_url,
            )
    except (ValueError, RuntimeError) as exc:
        # 友好提示而非让异常冒泡成 "后端无法连接"
        import sys

        import click

        from illusion.config.i18n import t as _t

        # Web 模式：优雅降级 — 用占位客户端继续启动，auth_status="missing"
        # 前端检测到 missing 会自动弹出 SettingsModal 引导用户配置
        # 终端模式：打印简短提示后 sys.exit(1)
        if "illusion.ui.web.ws_host" in sys.modules:
            logging.getLogger(__name__).warning("API client init failed (web mode, degraded): %s", exc)
            # 占位客户端：实际不会调用，用户配置后 _rebuild_api_client 会替换
            resolved_api_client = OpenAICompatibleClient(  # type: ignore[assignment]
                api_key="",
                base_url=settings.base_url,
            )
            _web_auth_missing = True
        else:
            click.echo(str(exc), err=True)
            click.echo(_t("terminal_auth_hint"), err=True)
            sys.exit(1)
    # 创建 MCP 客户端管理器（--bare 模式跳过自动发现，仅创建空管理器）
    if not bare:
        mcp_manager = McpClientManager(load_mcp_server_configs(settings, plugins, cwd))
        await mcp_manager.connect_all()
    else:
        # --bare 模式：空 MCP 管理器，不连接任何服务器
        # 注意：仍允许 --mcp-config 显式指定的服务器加载（见 Task 11）
        mcp_manager = McpClientManager({})
    # 创建工具注册器
    tool_registry = create_default_tool_registry(mcp_manager, is_interactive=is_interactive, channel_tools=channel_tools)
    # 获取桥接管理器
    bridge_manager = get_bridge_manager()
    # 创建应用状态存储
    app_state = AppStateStore(
        AppState(
            model=settings.active_model_name,
            permission_mode=settings.permission.mode.value,
            ui_language=settings.ui_language,
            cwd=cwd,
            auth_status="missing" if _web_auth_missing else auth_status(settings),
            base_url=settings.base_url or "",
            fast_mode=settings.fast_mode,
            effort=settings.effort,
            passes=settings.passes,
            mcp_connected=sum(1 for status in mcp_manager.list_statuses() if status.state == "connected"),
            mcp_failed=sum(1 for status in mcp_manager.list_statuses() if status.state == "failed"),
            bridge_sessions=len(bridge_manager.list_sessions()),
            output_style=settings.output_style,
            show_thinking=settings.show_thinking,
            phase="idle",
            session_id=session_id,
        )
    )
    # 创建会话钩子存储和钩子执行器
    from illusion.hooks.session_hooks import SessionHookStore
    session_hook_store = SessionHookStore()
    hook_executor = HookExecutor(
        load_hook_registry(settings, plugins),
        HookExecutionContext(
            cwd=Path(cwd).resolve(),
            api_client=resolved_api_client,
            default_model=settings.active_model_name,
        ),
        session_hook_store=session_hook_store,
    )
    # 创建权限检查器并同步沙箱限制
    permission_checker = PermissionChecker(settings.permission)
    permission_checker.sync_sandbox_restrictions(settings.sandbox)

    # 创建查询引擎
    engine = QueryEngine(
        api_client=resolved_api_client,
        tool_registry=tool_registry,
        permission_checker=permission_checker,
        cwd=cwd,
        model=settings.active_model_name,
        system_prompt=_build_system_prompt_with_append(
            settings,
            cwd=cwd,
            latest_user_prompt=prompt,
            channel_hint=channel_hint,
            append_system_prompt=append_system_prompt,
        ),
        max_tokens=settings.max_tokens,
        max_turns=settings.max_turns,
        permission_prompt=permission_prompt,
        ask_user_prompt=ask_user_prompt,
        plan_approval_prompt=plan_approval_prompt,
        hook_executor=hook_executor,
        tool_metadata={
            "mcp_manager": mcp_manager,
            "bridge_manager": bridge_manager,
            "app_state_store": app_state,
            "session_id": session_id,
            "session_hook_store": session_hook_store,
        },
        effort=EffortMapper.normalize(settings.effort),
        session_id=session_id,
    )
    # 将引擎自身添加到工具元数据中，供子 agent 使用
    engine._tool_metadata["query_engine"] = engine
    # 将后台代理追踪器添加到工具元数据中，供 AgentTool 使用
    engine._tool_metadata["bg_agent_tracker"] = engine._bg_agent_tracker

    # 注册 on_task_complete 回调：后台任务完成后通知 bg_agent_tracker
    # 闭包仅捕获 engine._bg_agent_tracker，实际逻辑委托给模块级 _on_task_complete
    def _on_task_complete_callback(task_id: str, task: "TaskRecord") -> None:
        _on_task_complete(task_id, task, engine._bg_agent_tracker)

    from illusion.tasks.manager import get_task_manager
    get_task_manager().on_task_complete = _on_task_complete_callback
    # 从保存的会话恢复消息（如果提供）
    if restore_messages:
        restored = [
            ConversationMessage.model_validate(m) for m in restore_messages
        ]
        engine.load_messages(restored)

    return RuntimeBundle(
        api_client=resolved_api_client,
        cwd=cwd,
        mcp_manager=mcp_manager,
        tool_registry=tool_registry,
        app_state=app_state,
        hook_executor=hook_executor,
        engine=engine,
        commands=create_default_command_registry(),
        external_api_client=api_client is not None,
        session_id=session_id,
        settings_overrides=settings_overrides,
        channel_hint=channel_hint,
    )


async def start_runtime(bundle: RuntimeBundle) -> AggregatedHookResult:
    """运行会话开始钩子。

    执行 SESSION_START 钩子事件，提取 additional_contexts
    并注入到系统提示词中（对齐 Claude Code 的 SessionStart 钩子行为）。

    Args:
        bundle: 运行时数据 bundle

    Returns:
        AggregatedHookResult: 钩子执行结果
    """
    result = await bundle.hook_executor.execute(
        HookEvent.SESSION_START,
        {"cwd": str(bundle.cwd), "source": "startup"},
    )
    # 存储 additionalContext，在 handle_line 中每次重建系统提示词后追加
    bundle.hook_additional_contexts = result.additional_contexts
    # 首次注入
    for ctx in result.additional_contexts:
        if ctx:
            current_prompt = bundle.engine._system_prompt
            bundle.engine.set_system_prompt(
                current_prompt + "\n\n" + _wrap_in_system_reminder(ctx)
            )
    return result


def _wrap_in_system_reminder(content: str) -> str:
    """向后兼容别名。"""
    from illusion.hooks.utils import wrap_in_system_reminder
    return wrap_in_system_reminder(content)


async def close_runtime(bundle: RuntimeBundle) -> None:
    """关闭运行时拥有的资源。

    关闭 MCP 管理器并执行 SESSION_END 钩子。

    Args:
        bundle: 运行时数据 bundle
    """
    from illusion.swarm.team_helpers import cleanup_session_teams

    await cleanup_session_teams()
    # 关闭 MCP 管理器
    await bundle.mcp_manager.close()
    # 执行会话结束钩子
    await bundle.hook_executor.execute(
        HookEvent.SESSION_END,
        {"cwd": str(bundle.cwd), "reason": "other"},
    )


def _last_user_text(messages: list[ConversationMessage]) -> str:
    """获取最后一条用户消息的文本。

    Args:
        messages: 会话消息列表

    Returns:
        str: 最后一条用户消息文本（如果不存在则返回空字符串）
    """
    for msg in reversed(messages):
        if msg.role == "user" and msg.text.strip():
            return msg.text.strip()
    return ""


def _truncate(text: str, limit: int) -> str:
    """截断文本到指定长度。

    Args:
        text: 要截断的文本
        limit: 最大长度

    Returns:
        str: 截断后的文本
    """
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _format_pending_tool_results(messages: list[ConversationMessage]) -> str | None:
    """在工具执行后停止时呈现紧凑摘要。

    在模型有机会响应之前呈现待处理结果的摘要。

    Args:
        messages: 会话消息列表

    Returns:
        str | None: 摘要文本（如果没有待处理结果则返回 None）
    """
    if not messages:
        return None

    last = messages[-1]
    if last.role != "user":
        return None
    tool_results = [block for block in last.content if isinstance(block, ToolResultBlock)]
    if not tool_results:
        return None

    # 构建工具使用 ID 到工具使用的映射
    tool_uses_by_id: dict[str, ToolUseBlock] = {}
    assistant_text = ""
    for msg in reversed(messages[:-1]):
        if msg.role != "assistant":
            continue
        if not msg.tool_uses:
            continue
        assistant_text = msg.text.strip()
        for tu in msg.tool_uses:
            tool_uses_by_id[tu.id] = tu
        break

    lines: list[str] = [
        "Pending continuation: tool results were produced, but the model did not get a chance to respond yet."
    ]
    if assistant_text:
        lines.append(f"Last assistant message: {_truncate(assistant_text, 400)}")

    max_results = 3
    for tr in tool_results[:max_results]:
        matching_tu: ToolUseBlock | None = tool_uses_by_id.get(tr.tool_use_id)
        if matching_tu is not None:
            raw_input = json.dumps(matching_tu.input, ensure_ascii=True, sort_keys=True)
            lines.append(
                f"- {matching_tu.name} {_truncate(raw_input, 200)} -> {_truncate(tr.content.strip() if isinstance(tr.content, str) else str(tr.content), 400)}"
            )
        else:
            lines.append(
                f"- tool_result[{tr.tool_use_id}] -> {_truncate(tr.content.strip() if isinstance(tr.content, str) else str(tr.content), 400)}"
            )

    if len(tool_results) > max_results:
        lines.append(f"(+{len(tool_results) - max_results} more tool results)")

    lines.append("To continue from these results, run: /continue 32 (or any count).")
    return "\n".join(lines)


def sync_app_state(bundle: RuntimeBundle) -> None:
    """从当前设置和动态键绑定刷新 UI 状态。

    Args:
        bundle: 运行时数据 bundle
    """
    from illusion.services.compact import estimate_conversation_tokens
    settings = bundle.current_settings()
    bundle.engine.set_max_turns(settings.max_turns)
    bundle.app_state.set(
        model=settings.active_model_name,
        permission_mode=settings.permission.mode.value,
        ui_language=settings.ui_language,
        cwd=bundle.cwd,
        auth_status=auth_status(settings),
        base_url=settings.base_url or "",
        fast_mode=settings.fast_mode,
        effort=settings.effort,
        passes=settings.passes,
        mcp_connected=sum(1 for status in bundle.mcp_manager.list_statuses() if status.state == "connected"),
        mcp_failed=sum(1 for status in bundle.mcp_manager.list_statuses() if status.state == "failed"),
        bridge_sessions=len(get_bridge_manager().list_sessions()),
        output_style=settings.output_style,
        show_thinking=settings.show_thinking,
        phase=bundle.app_state.get().phase,
        session_id=bundle.session_id,
        context_window=settings.context_window,
        context_tokens=estimate_conversation_tokens(bundle.engine.messages),
    )


def _rebuild_api_client(bundle: RuntimeBundle, settings: Settings) -> None:
    """根据当前设置重建 API 客户端（跨 env 切换模型时调用）

    当 API key 缺失或无效时，设置 auth_status="missing" 并返回，
    而非抛出异常导致后端崩溃。

    Args:
        bundle: 运行时数据 bundle
        settings: 当前设置
    """
    try:
        _api_format = settings.api_format
        if _api_format == "copilot":
            from illusion.auth.copilot import CopilotAuth, copilot_extra_headers
            _copilot = CopilotAuth()
            _copilot_token = _copilot.get_valid_token()
            new_client = OpenAICompatibleClient(
                api_key=_copilot_token,
                base_url=settings.base_url or "https://api.githubcopilot.com",
                extra_headers=copilot_extra_headers(),
            )
        elif _api_format == "codex":
            from illusion.auth.codex_oauth import CodexOAuth
            from illusion.api.codex_client import CodexApiClient
            new_client = CodexApiClient(  # type: ignore[assignment]
                auth_token_resolver=CodexOAuth().get_valid_token,
                base_url=settings.base_url,
            )
        elif _api_format == "anthropic":
            new_client = AnthropicApiClient(  # type: ignore[assignment]
                api_key=settings.resolve_api_key(),
                base_url=settings.base_url,
            )
        else:  # "openai" 及其他 OpenAI 兼容格式
            new_client = OpenAICompatibleClient(
                api_key=settings.resolve_api_key(),
                base_url=settings.base_url,
            )
    except (ValueError, RuntimeError) as exc:
        # 不退出，设置 auth_status 为 missing 并返回
        # web 前端会检测到 missing 状态并弹出设置弹窗
        logging.getLogger(__name__).warning("API client rebuild failed: %s", exc)
        try:
            bundle.app_state.get().auth_status = "missing"
        except Exception:
            pass
        return

    bundle.api_client = new_client  # type: ignore[assignment]
    bundle.engine.set_api_client(new_client)  # type: ignore[arg-type]
    bundle.hook_executor._context.api_client = new_client  # type: ignore[assignment]


async def handle_line(
    bundle: RuntimeBundle,
    line: str,
    *,
    print_system: SystemPrinter,
    render_event: StreamRenderer,
    clear_output: ClearHandler,
    replay_transcript_item: TranscriptItemSender | None = None,
    command_result_emitter: CommandResultEmitter | None = None,
    replace_transcript_items: ReplaceTranscriptItems | None = None,
) -> bool:
    """处理提交的一行输入（用于无头或 TUI 渲染）。

    处理命令或用户消息，更新引擎，渲染事件，并保存会话快照。

    Args:
        bundle: 运行时数据 bundle
        line: 用户输入的行
        print_system: 系统消息打印回调
        render_event: 流式事件渲染回调
        clear_output: 清空输出回调
        replay_transcript_item: 重播 transcript_item 的回调（用于 /resume）
        command_result_emitter: 指令结果发射回调
        replace_transcript_items: 替换转录项列表的回调（用于 /rewind 等，避免 Ink Static 重复渲染）

    Returns:
        bool: 是否继续会话
    """
    # 更新钩子注册表（如果不是外部 API 客户端）
    if not bundle.external_api_client:
        bundle.hook_executor.update_registry(
            load_hook_registry(bundle.current_settings(), bundle.current_plugins())
        )

    # 解析命令
    parsed = bundle.commands.lookup(line)
    if parsed is not None:
        command, args = parsed
        result = await command.handler(
            args,
            CommandContext(
                engine=bundle.engine,
                hooks_summary=bundle.hook_summary(),
                mcp_summary=bundle.mcp_summary(),
                plugin_summary=bundle.plugin_summary(),
                cwd=bundle.cwd,
                tool_registry=bundle.tool_registry,
                app_state=bundle.app_state,
                session_id=bundle.session_id,
                channel_hint=bundle.channel_hint,
            ),
        )
        if result.reset_session:
            bundle.session_id = uuid4().hex[:12]
            locale = str(bundle.app_state.get().ui_language or bundle.current_settings().ui_language)
            prefix = "新会话已开启，任务 ID：" if locale.lower().startswith("zh") else "Started new session. Task ID: "
            suffix = result.message or ""
            detail = f"\n{suffix}" if suffix else ""
            result.message = f"{prefix}{bundle.session_id}{detail}"
        await _render_command_result(result, print_system, clear_output, render_event, replay_transcript_item, command_result_emitter, replace_transcript_items)
        if result.restored_session_id:
            bundle.session_id = result.restored_session_id
        # 跨 env 切换模型时重建 API 客户端
        if result.needs_api_rebuild:
            _rebuild_api_client(bundle, bundle.current_settings())
        # 处理待继续标志
        if result.continue_pending:
            settings = bundle.current_settings()
            bundle.engine.set_max_turns(settings.max_turns)
            system_prompt = build_runtime_system_prompt(
                settings,
                cwd=bundle.cwd,
                latest_user_prompt=_last_user_text(bundle.engine.messages),
                channel_hint=bundle.channel_hint,
            )
            for ctx in bundle.hook_additional_contexts:
                if ctx:
                    system_prompt = system_prompt + "\n\n" + _wrap_in_system_reminder(ctx)
            bundle.engine.set_system_prompt(system_prompt)
            turns = result.continue_turns if result.continue_turns is not None else bundle.engine.max_turns
            try:
                async for event in bundle.engine.continue_pending(max_turns=turns):
                    await render_event(event)
            except MaxTurnsExceeded as exc:
                await print_system(f"Stopped after {exc.max_turns} turns (max_turns).")
                pending = _format_pending_tool_results(bundle.engine.messages)
                if pending:
                    await print_system(pending)
            # 保存会话快照
            save_session_snapshot(
                cwd=bundle.cwd,
                model=settings.active_model_name,
                system_prompt=system_prompt,
                messages=bundle.engine.messages,
                usage=bundle.engine.total_usage,
                session_id=bundle.session_id,
            )
        sync_app_state(bundle)
        return not result.should_exit

    # 处理普通用户消息
    settings = bundle.current_settings()
    bundle.engine.set_max_turns(settings.max_turns)
    system_prompt = build_runtime_system_prompt(settings, cwd=bundle.cwd, latest_user_prompt=line, channel_hint=bundle.channel_hint)
    # 追加钩子注入的 additionalContext
    for ctx in bundle.hook_additional_contexts:
        if ctx:
            system_prompt = system_prompt + "\n\n" + _wrap_in_system_reminder(ctx)
    bundle.engine.set_system_prompt(system_prompt)
    try:
        async for event in bundle.engine.submit_message(line):
            await render_event(event)
    except MaxTurnsExceeded as exc:
        await print_system(f"Stopped after {exc.max_turns} turns (max_turns).")
        pending = _format_pending_tool_results(bundle.engine.messages)
        if pending:
            await print_system(pending)
        save_session_snapshot(
            cwd=bundle.cwd,
            model=settings.model,
            system_prompt=system_prompt,
            messages=bundle.engine.messages,
            usage=bundle.engine.total_usage,
            session_id=bundle.session_id,
        )
        sync_app_state(bundle)
        return True
    # 保存会话快照
    save_session_snapshot(
        cwd=bundle.cwd,
        model=settings.model,
        system_prompt=system_prompt,
        messages=bundle.engine.messages,
        usage=bundle.engine.total_usage,
        session_id=bundle.session_id,
    )
    sync_app_state(bundle)
    return True


async def _render_command_result(
	result: CommandResult,
	print_system: SystemPrinter,
	clear_output: ClearHandler,
	render_event: StreamRenderer | None = None,
	replay_transcript_item: TranscriptItemSender | None = None,
	command_result_emitter: CommandResultEmitter | None = None,
	replace_transcript_items: ReplaceTranscriptItems | None = None,
) -> None:
	"""渲染命令执行结果。

	Args:
		result: 命令执行结果
		print_system: 系统消息打印回调
		clear_output: 清空输出回调
		render_event: 流式事件渲染回调
		replay_transcript_item: 重播 transcript_item 的回调
		command_result_emitter: 指令结果发射回调
		replace_transcript_items: 替换转录项列表的回调
	"""
	if result.replay_messages and replace_transcript_items is not None:
		from illusion.engine.messages import ToolUseBlock, ToolResultBlock

		tool_uses_by_id: dict[str, dict[str, Any]] = {}
		# 第一遍：收集所有 tool_use_id 和 tool_result 的 tool_use_id
		all_tool_use_ids: set[str] = set()
		all_tool_result_ids: set[str] = set()
		for msg in result.replay_messages:
			for block in msg.content:
				if isinstance(block, ToolUseBlock):
					all_tool_use_ids.add(block.id)
				elif isinstance(block, ToolResultBlock):
					all_tool_result_ids.add(block.tool_use_id)

		replay_items: list[dict[str, Any]] = []
		for msg in result.replay_messages:
			if msg.role == "user":
				if msg.text.strip():
					replay_items.append({"role": "user", "text": msg.text})
				for block in msg.content:
					if isinstance(block, ToolResultBlock):
						tool_info = tool_uses_by_id.get(block.tool_use_id, {})
						replay_items.append({
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
				# 因为 tool_started 事件会在新回合中添加流式文本，避免重复显示。
				# 但保留 reasoning/thinking（思考过程不应丢失）。
				if has_tool_use:
					if reasoning:
						replay_items.append({"role": "assistant", "text": "", "reasoning": reasoning})
				elif assistant_text or reasoning:
					item = {"role": "assistant", "text": assistant_text}
					if reasoning:
						item["reasoning"] = reasoning
					replay_items.append(item)
				for block in msg.content:
					if isinstance(block, ToolUseBlock):
						# 跳过孤立的 tool_use（没有对应 tool_result 的）
						if block.id not in all_tool_result_ids:
							continue
						tool_uses_by_id[block.id] = {"name": block.name, "input": block.input}
						replay_items.append({
							"role": "tool",
							"text": f"{block.name} {json.dumps(block.input, ensure_ascii=True)}",
							"tool_name": block.name,
							"tool_input": block.input,
							"tool_use_id": block.id,
						})
		await replace_transcript_items(replay_items)
		if result.message and command_result_emitter is not None:
			await command_result_emitter(result.message, "info")
		return
	elif result.clear_screen:
		await clear_output()
		if result.replay_messages and render_event is not None:
			from illusion.engine.stream_events import AssistantTurnComplete
			from illusion.api.usage import UsageSnapshot
			from illusion.engine.messages import ToolUseBlock, ToolResultBlock

			await clear_output()
			# 收集所有 tool_use_id 和 tool_result 的 tool_use_id，用于过滤孤立 tool_use
			all_tool_result_ids2: set[str] = set()
			for msg in result.replay_messages:
				for block in msg.content:
					if isinstance(block, ToolResultBlock):
						all_tool_result_ids2.add(block.tool_use_id)

			tool_uses_by_id2: dict[str, dict[str, Any]] = {}
			for msg in result.replay_messages:
				if msg.role == "user":
					if msg.text.strip():
						if replay_transcript_item is not None:
							await replay_transcript_item({"role": "user", "text": msg.text})
						else:
							await print_system(f"> {msg.text}")
					for block in msg.content:
						if isinstance(block, ToolResultBlock) and replay_transcript_item is not None:
							tool_info = tool_uses_by_id2.get(block.tool_use_id, {})
							await replay_transcript_item({
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
					# 因为 tool_started 事件会在新回合中添加流式文本，避免重复显示。
					# 但保留 reasoning/thinking（思考过程不应丢失）。
					if has_tool_use:
						if reasoning and replay_transcript_item is not None:
							await replay_transcript_item({"role": "assistant", "text": "", "reasoning": reasoning})
					else:
						if replay_transcript_item is not None and (assistant_text or reasoning):
							item = {"role": "assistant", "text": assistant_text}
							if reasoning:
								item["reasoning"] = reasoning
							await replay_transcript_item(item)
						elif assistant_text:
							await render_event(AssistantTurnComplete(message=msg, usage=UsageSnapshot()))
					for block in msg.content:
						if isinstance(block, ToolUseBlock):
							# 跳过孤立的 tool_use（没有对应 tool_result 的）
							if block.id not in all_tool_result_ids2:
								continue
							tool_uses_by_id2[block.id] = {"name": block.name, "input": block.input}
							if replay_transcript_item is not None:
								await replay_transcript_item({
									"role": "tool",
									"text": f"{block.name} {json.dumps(block.input, ensure_ascii=True)}",
									"tool_name": block.name,
									"tool_input": block.input,
									"tool_use_id": block.id,
								})
	elif result.clear_screen:
		await clear_output()
	if result.message and not result.replay_messages:
		if command_result_emitter is not None:
			await command_result_emitter(result.message, "info")
		else:
			await print_system(result.message)
