"""
钩子类型定义
============

定义钩子执行的输入和输出类型，与 Claude Code 对齐。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BaseHookInput:
    """钩子输入基础字段，对齐 Claude Code BaseHookInput。

    所有钩子事件共享这些字段，事件特定字段通过 create_hook_input() 附加。
    """

    session_id: str
    transcript_path: str
    cwd: str
    permission_mode: str | None = None
    agent_id: str | None = None
    agent_type: str | None = None


def create_base_hook_input(
    session_id: str = "",
    transcript_path: str = "",
    cwd: str = "",
    permission_mode: str | None = None,
    agent_id: str | None = None,
    agent_type: str | None = None,
) -> BaseHookInput:
    """创建 BaseHookInput 的工厂函数。"""
    return BaseHookInput(
        session_id=session_id,
        transcript_path=transcript_path,
        cwd=cwd,
        permission_mode=permission_mode,
        agent_id=agent_id,
        agent_type=agent_type,
    )


def create_hook_input(
    base: BaseHookInput,
    **extra: Any,
) -> dict[str, Any]:
    """创建完整的钩子输入字典。

    将 BaseHookInput 序列化为 dict，然后合并事件特定字段。
    """
    result: dict[str, Any] = {
        "session_id": base.session_id,
        "transcript_path": base.transcript_path,
        "cwd": base.cwd,
    }
    if base.permission_mode is not None:
        result["permission_mode"] = base.permission_mode
    if base.agent_id is not None:
        result["agent_id"] = base.agent_id
    if base.agent_type is not None:
        result["agent_type"] = base.agent_type
    result.update(extra)
    return result


@dataclass(frozen=True)
class HookResult:
    """单个钩子执行结果。

    权威字段是 permission_behavior。
    blocked 和 reason 可以显式传入（向后兼容），也可以从 permission_behavior 派生。
    """

    hook_type: str
    success: bool
    output: str = ""
    # 对齐 Claude Code
    prevent_continuation: bool = False
    permission_behavior: str | None = None  # "allow" | "deny" | None
    blocking_error: str | None = None
    system_message: str | None = None
    hook_specific_output: dict[str, Any] | None = None
    # 向后兼容字段
    blocked: bool = False
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 如果未显式设置 blocked，从 permission_behavior 派生
        if not self.blocked and self.permission_behavior == "deny":
            object.__setattr__(self, "blocked", True)
        # 如果未显式设置 reason，从其他字段派生
        if not self.reason and self.blocked:
            derived = self.blocking_error or self.system_message or self.output
            if derived:
                object.__setattr__(self, "reason", derived)


@dataclass(frozen=True)
class AggregatedHookResult:
    """聚合钩子结果，对齐 Claude Code 的聚合逻辑。"""

    results: list[HookResult] = field(default_factory=list)

    @property
    def permission_behavior(self) -> str | None:
        """聚合权限行为：deny > ask > allow > None。"""
        behaviors = [r.permission_behavior for r in self.results if r.permission_behavior]
        if "deny" in behaviors:
            return "deny"
        if "ask" in behaviors:
            return "ask"
        if "allow" in behaviors:
            return "allow"
        return None

    @property
    def blocked(self) -> bool:
        return self.permission_behavior == "deny" or any(r.blocked for r in self.results)

    @property
    def reason(self) -> str:
        if self.permission_behavior == "deny":
            for r in self.results:
                if r.permission_behavior == "deny":
                    return r.blocking_error or r.system_message or r.output
        for r in self.results:
            if r.blocked:
                return r.reason or r.output
        return ""

    @property
    def system_message(self) -> str | None:
        messages = [r.system_message for r in self.results if r.system_message]
        return "\n".join(messages) if messages else None

    @property
    def hook_specific_output(self) -> dict[str, Any] | None:
        outputs = {}
        for r in self.results:
            if r.hook_specific_output:
                outputs.update(r.hook_specific_output)
        return outputs or None
