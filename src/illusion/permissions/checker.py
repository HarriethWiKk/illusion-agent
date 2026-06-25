"""
权限检查模块
============

本模块实现权限检查功能，用于控制工具执行的权限。

主要功能：
    - 检查工具是否允许执行
    - 支持路径级别的权限规则
    - 支持命令级别的权限规则
    - 根据权限模式决定是否需要用户确认

类说明：
    - PermissionDecision: 权限决策结果
    - PathRule: 路径权限规则
    - PermissionChecker: 权限检查器

使用示例：
    >>> from illusion.permissions import PermissionChecker, PermissionDecision, PermissionMode
    >>> from illusion.config.settings import PermissionSettings
    >>> checker = PermissionChecker(settings)
    >>> decision = checker.evaluate("Bash", is_read_only=False, file_path="/path/to/file")
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from typing import Any

from illusion.config.settings import PermissionSettings
from illusion.permissions.modes import PermissionMode

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PermissionDecision:
    """权限决策结果

    表示检查工具调用是否允许执行的结果。

    Attributes:
        allowed: 是否允许执行该工具
        requires_confirmation: 是否需要用户确认
        reason: 决策原因说明
        auto_blocked: 是否为系统自动阻止（如计划模式），而非用户显式拒绝
        sandbox_blocked: 是否被沙箱限制阻止（需要用户三选项确认）
        sandbox_denied_path: 被沙箱拒绝的路径（用于会话级允许）
    """

    allowed: bool  # 是否允许执行
    requires_confirmation: bool = False  # 是否需要用户确认
    reason: str = ""  # 决策原因
    auto_blocked: bool = False  # 系统自动阻止（计划模式等）
    sandbox_blocked: bool = False  # 被沙箱限制阻止
    sandbox_denied_path: str = ""  # 被沙箱拒绝的路径


@dataclass(frozen=True)
class PathRule:
    """基于 glob 模式的路径权限规则
    
    用于控制对特定路径的访问权限。
    
    Attributes:
        pattern: glob 模式字符串
        allow: True 表示允许，False 表示拒绝
    """

    pattern: str  # glob 模式
    allow: bool  # True = 允许, False = 拒绝


class PermissionChecker:
    """权限检查器
    
    根据配置的权限模式和规则评估工具使用权限。
    
    Attributes:
        _settings: 权限设置对象
        _path_rules: 解析后的路径规则列表
    
    使用示例：
        >>> checker = PermissionChecker(settings)
        >>> decision = checker.evaluate("Read", is_read_only=True)
    """

    def __init__(self, settings: PermissionSettings) -> None:
        """初始化权限检查器

        Args:
            settings: 权限设置对象
        """
        self._settings = settings
        # 进入计划模式前的权限模式，用于退出时恢复
        self._pre_plan_mode: PermissionMode | None = None
        # 当前计划文件路径（plan mode 下豁免写入限制）
        self._plan_file_path: str | None = None
        # 沙箱文件系统限制规则（通过 sync_sandbox_restrictions 设置）
        self._sandbox_path_rules: list[PathRule] = []
        # 会话级沙箱允许路径（不持久化，重启后清除）
        self._session_allowed_paths: set[str] = set()
        # 从设置中解析路径规则
        self._path_rules: list[PathRule] = []
        for rule in getattr(settings, "path_rules", []):
            pattern = getattr(rule, "pattern", None) or (rule.get("pattern") if isinstance(rule, dict) else None)
            allow = getattr(rule, "allow", True) if not isinstance(rule, dict) else rule.get("allow", True)
            if isinstance(pattern, str) and pattern.strip():
                self._path_rules.append(PathRule(pattern=pattern.strip(), allow=allow))
            else:
                log.warning(
                    "跳过路径规则，pattern 字段缺失为空或非字符串: %r",
                    rule,
                )

    @property
    def current_mode(self) -> PermissionMode:
        """返回当前权限模式。"""
        return self._settings.mode

    def set_mode(self, mode: PermissionMode) -> None:
        """立即切换权限模式，保存前一个模式以便恢复。

        仅在尚未保存前一个模式时才保存（防止重复调用覆盖原始模式）。

        Args:
            mode: 目标权限模式
        """
        if self._pre_plan_mode is None:
            self._pre_plan_mode = self._settings.mode
        self._settings.mode = mode

    def restore_mode(self) -> None:
        """恢复到进入计划模式之前的权限模式，并清理计划文件路径。"""
        if self._pre_plan_mode is not None:
            self._settings.mode = self._pre_plan_mode
            self._pre_plan_mode = None
        self._plan_file_path = None

    def set_plan_file(self, file_path: str) -> None:
        """设置当前计划文件路径，使其在 plan mode 下可写。

        路径会被规范化为 resolve 后的绝对路径，确保符号链接等场景下比较正确。

        Args:
            file_path: 计划文件的绝对路径
        """
        from pathlib import Path
        self._plan_file_path = str(Path(file_path).expanduser().resolve())

    def sync_sandbox_restrictions(self, sandbox_settings: Any) -> None:
        """将沙箱文件系统限制同步到权限规则

        使文件工具（Read/Edit/Write/Grep/Glob）也受沙箱路径限制约束。

        Args:
            sandbox_settings: SandboxSettings 对象
        """
        self._sandbox_path_rules = []
        if not getattr(sandbox_settings, "enabled", False):
            return

        fs = getattr(sandbox_settings, "filesystem", None)
        if fs is None:
            return

        for path in getattr(fs, "deny_write", []):
            if path:
                self._sandbox_path_rules.append(PathRule(pattern=path, allow=False))
        for path in getattr(fs, "deny_read", []):
            if path:
                self._sandbox_path_rules.append(PathRule(pattern=path, allow=False))

    def allow_sandbox_path_for_session(self, path: str) -> None:
        """将路径添加到会话级沙箱允许列表（不持久化）

        Args:
            path: 要允许的路径
        """
        self._session_allowed_paths.add(path)

    def clear_session_allowed_paths(self) -> None:
        """清空会话级沙箱允许列表"""
        self._session_allowed_paths.clear()

    def evaluate(
        self,
        tool_name: str,
        *,
        is_read_only: bool,
        file_path: str | None = None,
        command: str | None = None,
    ) -> PermissionDecision:
        """评估工具是否允许执行
        
        根据权限模式和规则检查工具是否可以立即执行。
        
        Args:
            tool_name: 工具名称
            is_read_only: 是否为只读工具
            file_path: 相关的文件路径
            command: 执行的命令字符串
        
        Returns:
            PermissionDecision: 权限决策结果
        """
        # 显式的工具拒绝列表
        if tool_name in self._settings.denied_tools:
            return PermissionDecision(allowed=False, reason=f"{tool_name} is explicitly denied")

        # 显式的工具允许列表
        if tool_name in self._settings.allowed_tools:
            return PermissionDecision(allowed=True, reason=f"{tool_name} is explicitly allowed")

        # 检查路径级别规则
        if file_path and self._path_rules:
            for rule in self._path_rules:
                if fnmatch.fnmatch(file_path, rule.pattern):
                    if not rule.allow:
                        return PermissionDecision(
                            allowed=False,
                            reason=f"Path {file_path} matches deny rule: {rule.pattern}",
                        )

        # 检查沙箱文件系统限制
        if file_path and self._sandbox_path_rules:
            # 检查会话级允许列表
            if file_path not in self._session_allowed_paths:
                for rule in self._sandbox_path_rules:
                    if fnmatch.fnmatch(file_path, rule.pattern):
                        if not rule.allow:
                            return PermissionDecision(
                                allowed=False,
                                reason=f"sandbox_restriction: {file_path}",
                                sandbox_blocked=True,
                                sandbox_denied_path=file_path,
                            )

        # 检查命令拒绝模式（例如拒绝 "rm -rf /"）
        if command:
            for pattern in getattr(self._settings, "denied_commands", []):
                if isinstance(pattern, str) and fnmatch.fnmatch(command, pattern):
                    return PermissionDecision(
                        allowed=False,
                        reason=f"Command matches deny pattern: {pattern}",
                    )

        # 完全自动模式：允许一切
        if self._settings.mode == PermissionMode.FULL_AUTO:
            return PermissionDecision(allowed=True, reason="Auto mode allows all tools")

        # 只读工具始终允许
        if is_read_only:
            return PermissionDecision(allowed=True, reason="read-only tools are allowed")

        # 计划模式：阻止变更工具（自动阻止，不终止查询循环），但豁免计划文件、退出工具和agent工具
        if self._settings.mode == PermissionMode.PLAN:
            if tool_name == "exit_plan_mode":
                return PermissionDecision(allowed=True, reason="ExitPlanMode is always allowed in plan mode")
            if tool_name == "agent":
                return PermissionDecision(allowed=True, reason="Agent tool is allowed in plan mode")
            if file_path and self._plan_file_path and file_path == self._plan_file_path:
                return PermissionDecision(allowed=True, reason="Plan file is writable in plan mode")
            return PermissionDecision(
                allowed=False,
                reason="Plan mode blocks mutating tools until the user exits plan mode",
                auto_blocked=True,
            )

        # 默认模式：变更工具需要确认
        return PermissionDecision(
            allowed=False,
            requires_confirmation=True,
            reason="Mutating tools require user confirmation in default mode",
        )
