"""
代理工具模块
============

本模块提供子代理派发工具，对齐标准 AgentTool 架构。

主要组件：
    - AgentTool: 启动子代理的工具
    - AgentToolInput: 工具输入参数模型

使用示例：
    >>> from illusion.tools import AgentTool
    >>> tool = AgentTool()
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from illusion.state import AppStateStore
from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult

logger = logging.getLogger(__name__)


class AgentToolInput(BaseModel):
    """代理工具输入参数。

    属性：
        description: 任务的简短描述（3-5 个词）
        prompt: 代理要执行的完整任务
        subagent_type: 代理类型（如 'general-purpose', 'Explore', 'worker'）
        model: 可选的模型覆盖
        run_in_background: 是否在后台运行
        name: 代理名称，用于通过 SendMessage 寻址
        team_name: 团队名称（保留字段）
        mode: 权限模式覆盖
        isolation: 隔离模式（'worktree'）
        cwd: 工作目录覆盖
    """

    description: str = Field(description="A short (3-5 word) description of the task")
    prompt: str = Field(description="The task for the agent to perform")
    subagent_type: str | None = Field(
        default=None,
        description="The type of specialized agent to use for this task",
    )
    model: str | None = Field(
        default=None,
        description="Optional model override for this agent",
    )
    run_in_background: bool = Field(
        default=False,
        description="Set to true to run this agent in the background",
    )
    name: str | None = Field(
        default=None,
        description="Name for the spawned agent. Makes it addressable via SendMessage",
    )
    team_name: str | None = Field(
        default=None,
        description="Team name for spawning (reserved)",
    )
    mode: str | None = Field(
        default=None,
        description="Permission mode override for the agent",
    )
    isolation: str | None = Field(
        default=None,
        description='Isolation mode. "worktree" creates a temporary git worktree',
    )
    cwd: str | None = Field(
        default=None,
        description="Absolute path to run the agent in",
    )


class AgentTool(BaseTool[AgentToolInput]):
    """启动子代理处理复杂、多步骤任务。

    用于启动专门的代理来自动处理复杂任务。每个代理类型都有特定的能力和工具。
    """

    name = "agent"
    description = """Launch a new agent to handle complex, multi-step tasks autonomously.

The Agent tool launches specialized agents that autonomously handle complex tasks. Each agent type has specific capabilities and tools available to it.

Available agent types and the tools they have access to:
- general-purpose: All tools available. General-purpose agent for researching complex questions, searching for code, and executing multi-step tasks.
- Explore: Fast read-only codebase exploration (Tools: Glob, Grep, Read, Bash). Disallows editing tools.
- Plan: Software architect for designing implementation plans (Tools: Glob, Grep, Read, Bash). Disallows editing tools.
- verification: Verification specialist for checking implementation correctness (Tools: Glob, Grep, Read, Bash). Disallows editing tools.
- illusion-guide: Documentation lookup for Illusion Code/SDK/API (Tools: Glob, Grep, Read, WebFetch, WebSearch).
- worker: Implementation-focused worker agent. All tools available.
- statusline-setup: Status line configuration agent (Tools: Read, Edit).

When using the Agent tool, specify a subagent_type parameter to select which agent type to use. If omitted, the general-purpose agent is used.

When NOT to use the Agent tool:
- If you want to read a specific file path, use the Read tool or the Glob tool instead
- If you are searching for a specific class definition, use the Glob tool instead
- If you are searching for code within a specific file or set of 2-3 files, use the Read tool instead

Usage notes:
- Always include a short description (3-5 words) summarizing what the agent will do
- Launch multiple agents concurrently whenever possible, to maximize performance; to do that, use a single message with multiple tool uses
- When the agent is done, it will return a single message back to you. The result returned by the agent is not visible to the user. To show the user the result, you should send a text message back to the user with a concise summary of the result.
- You can optionally run agents in the background using the run_in_background parameter. When an agent runs in the background, you will be automatically notified when it completes — do NOT sleep, poll, or proactively check on its progress. Continue with other work or respond to the user instead.
- **Foreground vs background**: Use foreground (default) when you need the agent's results before you can proceed. Use background when you have genuinely independent work to do in parallel.
- To continue a previously spawned agent, use SendMessage with the agent's ID or name as the `to` field.
- The agent's outputs should generally be trusted
- Clearly tell the agent whether you expect it to write code or just to do research (search, file reads, web fetches, etc.), since it is not aware of the user's intent
- If the user specifies that they want you to run agents "in parallel", you MUST send a single message with multiple Agent tool use content blocks.
- Use `isolation="worktree"` to run the agent in an isolated git worktree directory. This prevents the agent from affecting the main workspace. The worktree is automatically cleaned up when the agent completes.

## Writing the prompt

When spawning a fresh agent (with a `subagent_type`), it starts with zero context. Brief the agent like a smart colleague who just walked into the room — it hasn't seen this conversation, doesn't know what you've tried, doesn't understand why this task matters.
- Explain what you're trying to accomplish and why.
- Describe what you've already learned or ruled out.
- Give enough context about the surrounding problem that the agent can make judgment calls rather than just following a narrow instruction.
- If you need a short response, say so ("report in under 200 words").
- Lookups: hand over the exact command. Investigations: hand over the question — prescribed steps become dead weight when the premise is wrong.

Terse command-style prompts produce shallow, generic work.

**Never delegate understanding.** Don't write "based on your findings, fix the bug" or "based on the research, implement it." Those phrases push synthesis onto the agent instead of doing it yourself. Write prompts that prove you understood: include file paths, line numbers, what specifically to change."""

    input_model = AgentToolInput

    async def execute(self, arguments: AgentToolInput, context: ToolExecutionContext) -> ToolResult:
        """执行代理工具。

        Args:
            arguments: 工具输入参数。
            context: 工具执行上下文。

        Returns:
            ToolResult: 工具执行结果。
        """
        # 延迟导入以避免循环依赖
        from illusion.coordinator.agent_definitions import (
            get_agent_definition,
            get_all_agent_definitions,
        )
        from illusion.swarm.agent_executor import (
            AgentSpawnConfig,
            format_task_notification,
            run_agent_in_process,
            run_agent_subprocess,
        )

        # 解析代理定义
        agent_def = None
        if arguments.subagent_type:
            agent_def = get_agent_definition(arguments.subagent_type)
            if agent_def is None:
                available = [a.name for a in get_all_agent_definitions()]
                return ToolResult(
                    output=f"Agent type '{arguments.subagent_type}' not found. Available agents: {', '.join(available)}",
                    is_error=True,
                )

        # 确定工作目录
        cwd = arguments.cwd or str(context.cwd)

        # ------------------------------------------------------------------
        # 处理 worktree 隔离
        # ------------------------------------------------------------------
        worktree_manager = None
        worktree_info = None
        isolation = arguments.isolation

        if isolation == "worktree":
            from illusion.swarm.worktree import WorktreeManager, validate_worktree_slug

            worktree_manager = WorktreeManager()

            # 生成唯一的 worktree slug
            slug_name = arguments.name or arguments.subagent_type or "agent"
            slug_name = slug_name.replace(" ", "-").lower()
            slug = f"{slug_name}-{uuid.uuid4().hex[:8]}"
            try:
                validate_worktree_slug(slug)
            except ValueError:
                # 降级：清理非兼容字符
                import re as _re
                slug = _re.sub(r"[^a-zA-Z0-9._-]", "-", slug).strip("-") or "agent-worktree"

            try:
                worktree_info = await worktree_manager.create_worktree(
                    repo_path=Path(cwd),
                    slug=slug,
                )
                cwd = str(worktree_info.path)
                logger.info(
                    "[AgentTool] Created worktree for agent at: %s", worktree_info.path
                )
            except Exception as exc:
                return ToolResult(
                    output=f"Failed to create isolated worktree: {exc}",
                    is_error=True,
                )

        # 构建生成配置
        config = AgentSpawnConfig(
            name=arguments.name or arguments.subagent_type or "agent",
            prompt=arguments.prompt,
            cwd=cwd,
            agent_definition=agent_def,
            model=arguments.model,
            permission_mode=arguments.mode,
        )

        # 获取父级工具注册表
        parent_registry = context.metadata.get("tool_registry")
        if parent_registry is None:
            return ToolResult(
                output="Tool registry not available in execution context",
                is_error=True,
            )

        # 获取查询引擎（用于进程内执行）
        query_engine = context.metadata.get("query_engine")

        if query_engine is not None:
            # 从引擎构建 QueryContext
            from illusion.engine.query import QueryContext
            query_context = QueryContext(
                api_client=query_engine._api_client,
                tool_registry=query_engine._tool_registry,
                permission_checker=query_engine._permission_checker,
                cwd=query_engine._cwd,
                model=query_engine._model,
                system_prompt=query_engine._system_prompt,
                max_tokens=query_engine._max_tokens,
                max_turns=query_engine._max_turns,
                permission_prompt=query_engine._permission_prompt,
                ask_user_prompt=query_engine._ask_user_prompt,
                hook_executor=query_engine._hook_executor,
                effort=query_engine._effort,
            )
        else:
            query_context = None

        app_state_store = context.metadata.get("app_state_store")
        in_team_context = False
        if isinstance(app_state_store, AppStateStore):
            team_context = app_state_store.get().team_context
            if isinstance(team_context, dict) and team_context.get("teamName"):
                in_team_context = True

        has_parent_queue = context.metadata.get("parent_message_queue") is not None
        effective_run_in_background = arguments.run_in_background

        # 团队上下文中后台模式的通知链路可能不可用，仅记录日志提醒
        if effective_run_in_background and in_team_context and not has_parent_queue:
            logger.info(
                "[AgentTool] Background agent in team context without parent queue; "
                "completion notification will not be delivered to caller"
            )

        # 辅助函数：清理 worktree
        async def _cleanup_worktree() -> None:
            if worktree_info is not None and worktree_manager is not None:
                try:
                    await worktree_manager.remove_worktree(worktree_info.slug)
                    logger.info("[AgentTool] Cleaned up worktree: %s", worktree_info.slug)
                except Exception:
                    logger.exception("[AgentTool] Failed to cleanup worktree: %s", worktree_info.slug)

        if effective_run_in_background:
            # 异步模式：后台执行
            # 获取后台代理追踪器
            bg_tracker = context.metadata.get("bg_agent_tracker")

            if query_context is not None:
                # 进程内后台执行：注册到 BackgroundTaskManager
                from illusion.tasks.manager import get_task_manager

                manager = get_task_manager()
                # 先创建 record（async_task 稍后填充）
                task_record = manager.register_in_process_agent_task(
                    description=arguments.description,
                    cwd=cwd,
                    prompt=arguments.prompt,
                )
                agent_id = task_record.id  # 形如 a3f2c1b4

                # 注册到追踪器（用于通知唤醒主循环）
                if bg_tracker is not None:
                    bg_tracker.register(agent_id)

                async def _run_background() -> None:
                    from illusion.swarm.agent_executor import (
                        AgentExecutionContext,
                        TeammateMessage,
                        _register_agent,
                        _unregister_agent,
                    )

                    bg_ctx = AgentExecutionContext(
                        agent_id=agent_id,
                        agent_name=config.name,
                        agent_definition=agent_def,
                        prompt=config.prompt,
                        model=config.model,
                        cwd=Path(cwd),
                        permission_mode=config.permission_mode,
                    )
                    _register_agent(bg_ctx)

                    # 后台模式仅传递 on_activity 回调：对所有事件（含文本生成、
                    # 工具事件）刷新 bg_tracker 的活动时间戳，让主循环通过 idle
                    # 超时判断是否卡住，避免 30s 固定超时误退出 busy。
                    # 后台无前端进度展示需求，不传 on_progress（与 on_activity 职责重叠）。
                    async def _on_bg_activity(event_type: str) -> None:
                        if bg_tracker is not None:
                            bg_tracker.notify_activity(agent_id, event_type)

                    try:
                        result = await run_agent_in_process(
                            config,
                            query_context,
                            parent_registry,
                            is_async=True,
                            existing_context=bg_ctx,
                            on_activity=_on_bg_activity,
                        )
                        # 构建通知 XML
                        if result.notification:
                            notification_xml = format_task_notification(result.notification)
                        else:
                            status = "completed" if result.success else "failed"
                            summary = result.result_text or result.error or "Agent completed"
                            notification_xml = (
                                f"<task-notification><task-id>{agent_id}</task-id>"
                                f"<status>{status}</status><summary>{summary}</summary></task-notification>"
                            )
                        # 把最终结果文本累积到 task output
                        if result.result_text:
                            await manager.write_to_task_output(agent_id, result.result_text)
                        # 标记任务完成（更新 status/ended_at/result，触发 on_task_complete）
                        manager.complete_in_process_agent(
                            agent_id,
                            success=result.success,
                            result=result.result_text,
                        )
                        # 通知后台代理追踪器（唤醒主 agent）
                        if bg_tracker is not None:
                            bg_tracker.notify_completed(agent_id, notification_xml)
                        # 通知父代理（团队上下文）
                        parent_queue = context.metadata.get("parent_message_queue")
                        if parent_queue:
                            await parent_queue.put(TeammateMessage(
                                text=notification_xml,
                                from_agent="system",
                            ))
                    except asyncio.CancelledError:
                        # task_stop 取消时，标记为 killed
                        manager.complete_in_process_agent(
                            agent_id,
                            success=False,
                            result="Agent was stopped by task_stop",
                        )
                        if bg_tracker is not None:
                            bg_tracker.notify_completed(
                                agent_id,
                                f"<task-notification><task-id>{agent_id}</task-id>"
                                f"<status>killed</status><summary>Agent was stopped by task_stop</summary></task-notification>",
                            )
                        raise
                    except Exception:
                        logger.exception("[AgentTool] Background agent %s failed", agent_id)
                        manager.complete_in_process_agent(
                            agent_id,
                            success=False,
                            result="Agent crashed with unhandled exception",
                        )
                        # 即使异常也通知追踪器，避免主 agent 永远等待
                        if bg_tracker is not None:
                            bg_tracker.notify_completed(
                                agent_id,
                                f"<task-notification><task-id>{agent_id}</task-id>"
                                f"<status>failed</status><summary>Agent crashed with unhandled exception</summary></task-notification>",
                            )
                    finally:
                        _unregister_agent(agent_id)
                        await _cleanup_worktree()

                bg_async_task = asyncio.create_task(_run_background(), name=f"agent-{agent_id}")
                task_record.async_task = bg_async_task

                return ToolResult(
                    output=(
                        f"Agent '{config.name}' launched in background (task_id={agent_id}).\n"
                        "You will be automatically notified when it completes — do NOT sleep, poll, "
                        "or call task_output to check its progress. Continue with other work or "
                        "respond to the user instead."
                    ),
                )
            else:
                # 子进程后台执行 - worktree 清理由 WorktreeManager.cleanup_stale 负责
                if worktree_info is not None:
                    logger.info(
                        "[AgentTool] Worktree %s will persist for subprocess agent; "
                        "cleanup deferred to stale worktree cleanup",
                        worktree_info.slug,
                    )
                result = await run_agent_subprocess(config)
                if not result.success:
                    await _cleanup_worktree()
                    return ToolResult(output=result.error or "Failed to spawn agent", is_error=True)
                return ToolResult(
                    output=(
                        f"Agent '{config.name}' launched as subprocess (agent_id={result.agent_id}).\n"
                        "You will be automatically notified when it completes — do NOT sleep, poll, "
                        "or call task_output to check its progress. Continue with other work or "
                        "respond to the user instead."
                    ),
                )
        else:
            # 同步模式：前台执行
            try:
                if query_context is not None:
                    # 进程内同步执行，传入 on_progress 回调以流式上报子代理工具调用进度。
                    # 仅前台模式传递；后台模式由 task manager 负责状态追踪。
                    result = await run_agent_in_process(
                        config,
                        query_context,
                        parent_registry,
                        on_progress=context.on_progress,
                    )

                    if not result.success:
                        return ToolResult(output=result.error or "Agent execution failed", is_error=True)

                    return ToolResult(output=result.result_text)
                else:
                    # 子进程同步执行（不常见，但支持）
                    result = await run_agent_subprocess(config)
                    if not result.success:
                        return ToolResult(output=result.error or "Failed to spawn agent", is_error=True)
                    return ToolResult(
                        output=f"Agent '{config.name}' launched as subprocess (agent_id={result.agent_id}).",
                    )
            finally:
                await _cleanup_worktree()
