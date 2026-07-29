"""System overhead token 反推跟踪器。

通过 API 返回的 input_tokens（即 prompt_tokens）减去估算的 messages tokens，
反推得到 system overhead 实测值（含 system prompt / tools / skills / hooks / rules
/ memory / channels 等系统级开销），不拆分子项。

主要类：
    - SystemOverheadTracker: 反推并缓存 system overhead
"""

from __future__ import annotations

import hashlib


class SystemOverheadTracker:
    """反推并缓存 system overhead token 实测值。

    system_overhead = api_input_tokens - messages_tokens_estimated
    其中 api_input_tokens 为单轮 API 返回的 input_tokens（即 prompt_tokens，
    已含完整上下文：system + messages + tools + skills 等）。

    缓存在 system prompt 文本变化时失效。
    """

    def __init__(self) -> None:
        self._cached_overhead: int | None = None
        self._system_prompt_hash: str | None = None

    @property
    def has_measured_value(self) -> bool:
        """是否已得到实测值。"""
        return self._cached_overhead is not None

    @property
    def tokens(self) -> int | None:
        """返回实测值；未实测返回 None。"""
        return self._cached_overhead

    def invalidate(self, system_prompt_text: str) -> None:
        """system prompt 变化时失效缓存。

        Args:
            system_prompt_text: 当前 system prompt 文本
        """
        new_hash = hashlib.sha256(system_prompt_text.encode()).hexdigest()
        if new_hash != self._system_prompt_hash:
            self._cached_overhead = None
            self._system_prompt_hash = new_hash

    def update_from_usage(self, api_input_tokens: int, messages_tokens_estimated: int) -> bool:
        """API 响应后反推并缓存。

        Args:
            api_input_tokens: 本轮 API 返回的 input_tokens（即 prompt_tokens）
            messages_tokens_estimated: 估算的 messages tokens

        Returns:
            bool: 是否成功更新
        """
        if api_input_tokens <= 0 or messages_tokens_estimated < 0:
            return False
        overhead = api_input_tokens - messages_tokens_estimated
        # 边界：反推值异常（<=0 或 >500000）则丢弃
        if overhead <= 0 or overhead > 500_000:
            return False
        self._cached_overhead = overhead
        return True

    def reset(self) -> None:
        """重置到初始状态。"""
        self._cached_overhead = None
        self._system_prompt_hash = None
