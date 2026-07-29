"""System overhead token 反推跟踪器。

通过 API 返回的 input_tokens（即 prompt_tokens）减去估算的 messages tokens，
反推得到 system overhead 实测值（含 system prompt / tools / skills / hooks / rules
/ memory / channels 等系统级开销），不拆分子项。

每轮 API 调用后无条件反推覆盖，接受自然波动。不使用 hash 比对，因为
system_prompt 文本不包含 tools 描述，hash 无法完整代表系统级开销变化。

主要类：
    - SystemOverheadTracker: 反推并缓存 system overhead
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from illusion.services.checkpoint_store import RestoreResult


class SystemOverheadTracker:
    """反推并缓存 system overhead token 实测值。

    system_overhead = api_input_tokens - messages_tokens_estimated
    其中 api_input_tokens 为单轮 API 返回的 input_tokens（即 prompt_tokens，
    已含完整上下文：system + messages + tools + skills 等）。

    每轮 API 调用后由 update_from_usage 无条件反推覆盖。
    """

    def __init__(self) -> None:
        self._cached_overhead: int | None = None

    @property
    def has_measured_value(self) -> bool:
        """是否已得到实测值。"""
        return self._cached_overhead is not None

    @property
    def tokens(self) -> int | None:
        """返回实测值；未实测返回 None。"""
        return self._cached_overhead

    def update_from_usage(self, api_input_tokens: int, messages_tokens_estimated: int) -> bool:
        """API 响应后反推并缓存。

        每轮无条件覆盖（只要反推值在合法范围内），接受自然波动。

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

    def apply_restore(self, result: RestoreResult) -> None:
        """从 CheckpointStore.restore() 结果恢复 overhead。

        resume 后使用持久化的 overhead 值显示，直到下一轮 API 调用反推覆盖。

        Args:
            result: restore 结果
        """
        if result.system_overhead is not None and result.system_overhead > 0:
            self._cached_overhead = result.system_overhead
        else:
            self.reset()

    def reset(self) -> None:
        """重置到初始状态。"""
        self._cached_overhead = None
