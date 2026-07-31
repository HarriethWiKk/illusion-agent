"""
Token 估算与上下文窗口工具函数。
"""

from __future__ import annotations

import logging

from illusion.engine.messages import (
    ConversationMessage,
    MediaBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from illusion.services.compact.constants import (
    _DEFAULT_CONTEXT_WINDOW,
    AUTOCOMPACT_BUFFER_TOKENS,
    MANUAL_COMPACT_BUFFER_TOKENS,
    MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES,
    MAX_OUTPUT_TOKENS_FOR_SUMMARY,
    TOKEN_ESTIMATION_PADDING,
    WARNING_THRESHOLD_BUFFER_TOKENS,
)
from illusion.services.compact.models import AutoCompactState, TokenWarningState
from illusion.services.token_estimation import estimate_tokens

log = logging.getLogger(__name__)


def estimate_message_tokens(messages: list[ConversationMessage]) -> int:
    """估算会话消息的总 Token 数，包含 4/3 padding。"""
    total = 0
    for msg in messages:
        for block in msg.content:
            if isinstance(block, TextBlock):
                total += estimate_tokens(block.text)
            elif isinstance(block, ToolResultBlock):
                if isinstance(block.content, str):
                    total += estimate_tokens(block.content)
                elif isinstance(block.content, list):
                    for inner in block.content:
                        if isinstance(inner, TextBlock):
                            total += estimate_tokens(inner.text)
                        elif isinstance(inner, MediaBlock):
                            total += 2000
            elif isinstance(block, ToolUseBlock):
                total += estimate_tokens(block.name)
                total += estimate_tokens(str(block.input))
            elif isinstance(block, ThinkingBlock):
                total += estimate_tokens(block.thinking)
                if block.signature:
                    total += estimate_tokens(block.signature)
            elif isinstance(block, MediaBlock):
                total += 2000
    return int(total * TOKEN_ESTIMATION_PADDING)


def estimate_conversation_tokens(messages: list[ConversationMessage]) -> int:
    """保持向后兼容性的别名。"""
    return estimate_message_tokens(messages)


def get_context_window() -> int:
    """返回当前配置的上下文窗口大小。

    Returns:
        int: 上下文窗口 token 数
    """
    from illusion.config.settings import load_settings

    settings = load_settings()
    if settings.context_window and settings.context_window > 0:
        return settings.context_window

    return _DEFAULT_CONTEXT_WINDOW


def get_autocompact_threshold(model: str) -> int:
    """计算触发自动压缩的 Token 数量阈值。"""
    context_window = get_context_window()
    reserved = min(MAX_OUTPUT_TOKENS_FOR_SUMMARY, 20_000)
    effective = context_window - reserved
    return effective - AUTOCOMPACT_BUFFER_TOKENS


def calculate_token_warning_state(
    messages: list[ConversationMessage],
    model: str,
    *,
    auto_compact_enabled: bool = True,
) -> TokenWarningState:
    """计算当前上下文使用量的警告状态。"""
    estimated = estimate_message_tokens(messages)
    context_window = get_context_window()
    threshold = get_autocompact_threshold(model)

    is_above_autocompact = estimated >= threshold
    is_above_warning = estimated >= (threshold - WARNING_THRESHOLD_BUFFER_TOKENS)
    is_at_blocking = (
        not auto_compact_enabled
        and estimated >= (context_window - MANUAL_COMPACT_BUFFER_TOKENS)
    )

    return TokenWarningState(
        is_above_warning_threshold=is_above_warning,
        is_above_autocompact_threshold=is_above_autocompact,
        is_at_blocking_limit=is_at_blocking,
        estimated_tokens=estimated,
        threshold=threshold,
        context_window=context_window,
    )


def should_autocompact(
    messages: list[ConversationMessage],
    model: str,
    state: AutoCompactState,
    system_overhead: int | None = None,
) -> bool:
    """返回是否应该自动压缩会话。

    使用与 /context usage 相同的计算方式：
    Estimated Used = System Prompt(system_overhead) + Messages(message_tokens)

    Args:
        messages: 会话消息列表
        model: 模型名称
        state: 自动压缩状态
        system_overhead: 系统开销实测值（system prompt + tools + skills 等）
    """
    if state.consecutive_failures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES:
        return False
    message_tokens = estimate_message_tokens(messages)
    # 与 /context usage 保持一致：总 token = 系统开销 + 消息 token
    token_count = message_tokens + (system_overhead or 0)
    threshold = get_autocompact_threshold(model)
    return token_count >= threshold
