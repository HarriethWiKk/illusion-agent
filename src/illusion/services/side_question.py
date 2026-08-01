"""
一次性侧问服务
==============

在不打断主对话的前提下发起多轮 LLM 查询，复用 QueryEngine 当前上下文。

核心设计：
    - 不写入 engine.messages（使用副本）
    - 不触发 hooks（QueryContext.hook_executor=None）
    - 不触发权限提示（permission_prompt/ask_user_prompt/plan_approval_prompt=None）
    - 拒绝所有工具调用（deny_all_tools=True），防止工作区污染
    - 使用独立的 file_state_cache 和 overhead_tracker，避免污染主会话状态
    - 只收集最后一轮助手消息的纯文本回复返回给调用方

设计要点：
    - 复用 run_query 而非手写循环，确保工具调用、权限、自动压缩等行为与主对话一致
    - max_turns=8（多轮），允许模型在工具被拒绝后调整行为直接回答
    - deny_all_tools=True：拒绝所有工具调用，返回友好错误消息
    - hook_executor=None：侧问不应触发用户配置的 hooks（如 stop hook 阻塞）
    - 不传 permission_prompt 等回调：侧问期间不应弹窗打断用户
    - 状态隔离：独立的 file_state_cache 和 overhead_tracker，避免污染主会话

主要组件：
    - SideQuestionError: 侧问查询失败异常
    - run_side_question: 发起一次性侧问，返回最终纯文本回复

使用示例：
    >>> reply = await run_side_question("What is 2+2?", engine)
    >>> reply
    '4'
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from illusion.engine.messages import ConversationMessage
from illusion.engine.query import QueryContext, run_query
from illusion.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    ToolExecutionStarted,
)

if TYPE_CHECKING:
    from illusion.engine.query_engine import QueryEngine
    from illusion.state import AppStateStore

logger = logging.getLogger(__name__)

# 侧问最大轮次
_SIDE_QUESTION_MAX_TURNS = 8


class SideQuestionError(Exception):
    """侧问查询失败。"""


def _extract_side_question_reply(events: list[Any]) -> str:
    """从侧问事件列表中提取最终回复文本。

    优雅处理工具调用尝试：如果模型尝试调用工具而非直接回答，
    返回友好的错误提示（i18n）。

    Args:
        events: run_query 产生的事件列表

    Returns:
        str: 提取的回复文本
    """
    from illusion.config.i18n import t

    text_parts: list[str] = []
    has_tool_attempt = False
    attempted_tool_name = ""

    for event in events:
        if isinstance(event, AssistantTextDelta):
            text_parts.append(event.text)
        elif isinstance(event, ToolExecutionStarted):
            has_tool_attempt = True
            attempted_tool_name = event.tool_name

    # 优先使用收集的文本
    text = "".join(text_parts).strip()
    if text:
        return text

    # 无文本但有工具调用尝试
    if has_tool_attempt:
        return t("side_question_tool_attempt", tool_name=attempted_tool_name)

    return ""


async def run_side_question(
    question: str,
    engine: QueryEngine,
    app_state: AppStateStore | None = None,
) -> str:
    """发起一次性侧问，返回最终纯文本回复。

    复用 engine 的 API 客户端、工具注册表、权限检查器等，在主对话消息历史
    副本上追加本次侧问，执行多轮查询（最多 8 轮），只提取助手消息的纯文本内容返回。

    关键设计：
    - deny_all_tools=True：拒绝所有工具调用，防止工作区污染
    - 独立的 file_state_cache 和 overhead_tracker：避免污染主会话状态
    - max_turns=8：允许模型在工具被拒绝后调整行为直接回答

    Args:
        question: 用户的侧问内容
        engine: 当前会话的 QueryEngine（只读访问其配置和工具集）
        app_state: 应用状态（保留参数，当前未使用）

    Returns:
        str: 最终助手消息的纯文本回复

    Raises:
        SideQuestionError: LLM 查询失败时抛出
    """
    del app_state  # 预留

    # 复制当前消息历史，剥离末尾未完成的 assistant 消息
    messages = list(engine.messages)
    while messages and messages[-1].role == "assistant":
        messages.pop()

    # 追加本次侧问作为 user 消息
    messages.append(ConversationMessage.from_user_text(question))

    # 创建独立的 file_state_cache 和 overhead_tracker，避免污染主会话状态
    from illusion.services.compact.system_overhead_tracker import SystemOverheadTracker
    from illusion.utils.file_state_cache import FileStateCache

    isolated_file_state_cache = FileStateCache()
    isolated_overhead_tracker = SystemOverheadTracker()

    # 构建 QueryContext：复用 engine 的工具/权限/API，但禁用 hooks 和交互回调
    context = QueryContext(
        api_client=engine.api_client,
        tool_registry=engine.tool_registry,
        permission_checker=engine.permission_checker,
        cwd=engine.cwd,
        model=engine.model,
        system_prompt=engine.system_prompt or "",
        max_tokens=engine.max_tokens,
        max_turns=_SIDE_QUESTION_MAX_TURNS,
        permission_prompt=None,
        ask_user_prompt=None,
        plan_approval_prompt=None,
        hook_executor=None,
        tool_metadata=engine.tool_metadata or None,
        effort=engine.effort,
        bg_agent_tracker=None,
        bg_agent_wait_timeout=300.0,
        compact_state=None,
        overhead_tracker=isolated_overhead_tracker,  # 隔离：独立实例
        on_before_tool_execute=None,
        file_state_cache=isolated_file_state_cache,  # 隔离：独立实例
        deny_all_tools=True,  # 拒绝所有工具调用
    )

    collected_events: list[Any] = []
    last_assistant_text: str = ""

    try:
        async for event, _usage in run_query(context, messages):
            collected_events.append(event)
            # 记录每轮完成的完整文本
            if isinstance(event, AssistantTurnComplete):
                last_assistant_text = event.message.text or ""
    except Exception as exc:
        logger.warning("[side_question] 查询失败: %s", exc)
        raise SideQuestionError(str(exc)) from exc

    # 优先使用最后一轮的完整文本（含 tool_use 之外的 text 块），
    # 若最后一轮无文本（纯工具调用结尾），回退到事件提取
    reply = last_assistant_text.strip()
    if not reply:
        reply = _extract_side_question_reply(collected_events)
    return reply
