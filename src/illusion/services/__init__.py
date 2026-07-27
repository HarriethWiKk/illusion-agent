"""
服务模块导出
==========

本模块导出 services 子目录中的公共接口。
"""

from __future__ import annotations

from illusion.services.compact import (
    AutoCompactState,
    TokenWarningState,
    calculate_token_warning_state,
    compact_conversation,
    compact_messages,
    create_compact_boundary_marker,
    estimate_conversation_tokens,
    get_autocompact_threshold,
    get_context_window,
    get_messages_after_compact_boundary,
    is_compact_boundary_marker,
    microcompact_messages,
    reactive_compact,
    should_autocompact,
    strip_images_from_messages,
    summarize_messages,
)
from illusion.services.session_storage import (
    export_session_markdown,
    get_project_session_dir,
    load_session_snapshot,
    save_session_snapshot,
)
from illusion.services.token_estimation import estimate_message_tokens, estimate_tokens

__all__ = [
    "AutoCompactState",
    "TokenWarningState",
    "calculate_token_warning_state",
    "compact_conversation",
    "compact_messages",
    "create_compact_boundary_marker",
    "estimate_conversation_tokens",
    "estimate_message_tokens",
    "estimate_tokens",
    "export_session_markdown",
    "get_autocompact_threshold",
    "get_context_window",
    "get_messages_after_compact_boundary",
    "get_project_session_dir",
    "is_compact_boundary_marker",
    "load_session_snapshot",
    "microcompact_messages",
    "reactive_compact",
    "save_session_snapshot",
    "should_autocompact",
    "strip_images_from_messages",
    "summarize_messages",
]
