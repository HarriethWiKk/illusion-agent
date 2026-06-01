"""
自动压缩与响应式压缩。
"""

from __future__ import annotations

import logging
from typing import Any

from illusion.engine.messages import ConversationMessage
from illusion.services.compact.compact_core import compact_conversation
from illusion.services.compact.constants import DEFAULT_KEEP_RECENT, DEFAULT_PRESERVE_RECENT, MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES
from illusion.services.compact.microcompact import microcompact_messages
from illusion.services.compact.models import AutoCompactState
from illusion.services.compact.token_utils import should_autocompact

log = logging.getLogger(__name__)


async def reactive_compact(
    messages: list[ConversationMessage],
    *,
    api_client: Any,
    model: str,
    system_prompt: str = "",
    preserve_recent: int = DEFAULT_PRESERVE_RECENT,
) -> tuple[list[ConversationMessage], bool]:
    """当 API 返回 prompt-too-long 错误时，尝试压缩并重试。"""
    log.info("Reactive compact triggered due to prompt-too-long error")

    messages, tokens_freed = microcompact_messages(messages, keep_recent=DEFAULT_KEEP_RECENT)
    if tokens_freed > 0:
        log.info("Reactive microcompact freed ~%d tokens", tokens_freed)
        return messages, True

    try:
        result = await compact_conversation(
            messages,
            api_client=api_client,
            model=model,
            system_prompt=system_prompt,
            preserve_recent=preserve_recent,
            suppress_follow_up=True,
        )
        return result, True
    except Exception as exc:
        log.error("Reactive compact failed: %s", exc)
        return messages, False


async def auto_compact_if_needed(
    messages: list[ConversationMessage],
    *,
    api_client: Any,
    model: str,
    system_prompt: str = "",
    state: AutoCompactState,
    preserve_recent: int = DEFAULT_PRESERVE_RECENT,
) -> tuple[list[ConversationMessage], bool]:
    """检查是否应该自动压缩，如果是则执行压缩。"""
    if not should_autocompact(messages, model, state):
        return messages, False

    log.info("Auto-compact triggered (failures=%d)", state.consecutive_failures)

    messages, tokens_freed = microcompact_messages(messages)
    if tokens_freed > 0 and not should_autocompact(messages, model, state):
        log.info("Microcompact freed ~%d tokens, auto-compact no longer needed", tokens_freed)
        state.warning_suppressed = True
        return messages, True

    try:
        result = await compact_conversation(
            messages,
            api_client=api_client,
            model=model,
            system_prompt=system_prompt,
            preserve_recent=preserve_recent,
            suppress_follow_up=True,
        )
        state.compacted = True
        state.turn_counter += 1
        state.last_compacted_at_turn = state.turn_counter
        state.consecutive_failures = 0
        state.warning_suppressed = True
        return result, True
    except Exception as exc:
        state.consecutive_failures += 1
        log.error(
            "Auto-compact failed (attempt %d/%d): %s",
            state.consecutive_failures,
            MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES,
            exc,
        )
        return messages, False
