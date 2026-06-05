"""沙箱模块公共 API

提供沙箱系统的统一入口：
- SandboxManager: 沙箱管理器单例
- SandboxRuntime: 核心运行时
- SandboxViolationStore: 违规事件存储
- SandboxAvailability: 可用性状态
- SandboxUnavailableError: 不可用异常
"""
from illusion.sandbox.adapter import (
    SandboxManager,
    SandboxAvailability,
    SandboxUnavailableError,
    build_sandbox_runtime_config,
    get_sandbox_availability,
    wrap_command_for_sandbox,
)
from illusion.sandbox.runtime import SandboxRuntime
from illusion.sandbox.violation_store import SandboxViolationStore, SandboxViolation

__all__ = [
    "SandboxManager",
    "SandboxAvailability",
    "SandboxUnavailableError",
    "SandboxRuntime",
    "SandboxViolationStore",
    "SandboxViolation",
    # 向后兼容
    "build_sandbox_runtime_config",
    "get_sandbox_availability",
    "wrap_command_for_sandbox",
]
