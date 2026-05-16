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


class AgentTool(BaseTool):
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
        from illusion.coordinator.agent_definitions import get_agent_definition, get_all_agent_definitions
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
        if effective_run_in_background and in_team_context and not has_parent_queue:
            logger.info(
                "[AgentTool] Team lead call forces foreground mode to keep task chain continuous"
            )
            effective_run_in_background = False

        if effective_run_in_background:
            # 异步模式：后台执行
            if query_context is not None:
                # 进程内后台执行
                agent_id = f"agent_{uuid.uuid4().hex[:12]}"

                async def _run_background():
                    from illusion.swarm.agent_executor import (
                        AgentExecutionContext,
                        set_agent_context,
                        _register_agent,
                        _unregister_agent,
                        TeammateMessage,
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

                    try:
                        result = await run_agent_in_process(config, query_context, parent_registry, is_async=True, existing_context=bg_ctx)
                        # 通知父代理
                        if result.notification:
                            notification_xml = format_task_notification(result.notification)
                            parent_queue = context.metadata.get("parent_message_queue")
                            if parent_queue:
                                await parent_queue.put(TeammateMessage(
                                    text=notification_xml,
                                    from_agent="system",
                                ))
                    except Exception:
                        logger.exception("[AgentTool] Background agent %s failed", agent_id)
                    finally:
                        _unregister_agent(agent_id)

                asyncio.create_task(_run_background(), name=f"agent-{agent_id}")

                return ToolResult(
                    output=(
                        f"Agent '{config.name}' launched in background (agent_id={agent_id}). "
                        f"You will be notified when it completes."
                    ),
                )
            else:
                # 子进程后台执行
                result = await run_agent_subprocess(config)
                if not result.success:
                    return ToolResult(output=result.error or "Failed to spawn agent", is_error=True)
                return ToolResult(
                    output=(
                        f"Agent '{config.name}' launched as subprocess (agent_id={result.agent_id}). "
                        f"You will be notified when it completes."
                    ),
                )
        else:
            # 同步模式：前台执行
            if query_context is not None:
                # 进程内同步执行
                result = await run_agent_in_process(config, query_context, parent_registry)

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
