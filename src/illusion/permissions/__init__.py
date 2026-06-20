"""
权限模块
========

本模块提供 IllusionCode 权限检查和管理功能。

主要组件：
    - PermissionChecker: 权限检查器
    - PermissionDecision: 权限决策
    - PermissionMode: 权限模式
    - ProjectPermissions: 项目级权限配置
    - load_project_permissions: 加载项目级权限配置

使用示例：
    >>> from illusion.permissions import PermissionChecker, PermissionMode, ProjectPermissions
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from illusion.permissions.checker import PermissionChecker, PermissionDecision
    from illusion.permissions.loader import load_project_permissions
    from illusion.permissions.modes import PermissionMode
    from illusion.permissions.schemas import ProjectPermissions

__all__ = [
    "PermissionChecker",
    "PermissionDecision",
    "PermissionMode",
    "ProjectPermissions",
    "load_project_permissions",
]


def __getattr__(name: str):
    if name in {"PermissionChecker", "PermissionDecision"}:
        from illusion.permissions.checker import PermissionChecker, PermissionDecision

        return {
            "PermissionChecker": PermissionChecker,
            "PermissionDecision": PermissionDecision,
        }[name]
    if name == "PermissionMode":
        from illusion.permissions.modes import PermissionMode

        return PermissionMode
    if name == "ProjectPermissions":
        from illusion.permissions.schemas import ProjectPermissions

        return ProjectPermissions
    if name == "load_project_permissions":
        from illusion.permissions.loader import load_project_permissions

        return load_project_permissions
    raise AttributeError(name)
