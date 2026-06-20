"""
项目级权限加载模块
================

本模块提供从项目目录加载权限配置的功能。

主要功能：
    - load_project_permissions: 加载项目级权限配置

使用示例：
    >>> from illusion.permissions.loader import load_project_permissions
    >>> perms = load_project_permissions("/path/to/project")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from illusion.config.paths import get_project_config_dir
from illusion.permissions.schemas import ProjectPermissions

logger = logging.getLogger(__name__)


def load_project_permissions(cwd: str | Path) -> ProjectPermissions:
    """加载项目级权限配置

    从 `<project>/.illusion/permissions.json` 文件中读取权限配置。
    如果文件不存在或字段缺失，返回默认值。

    Args:
        cwd: 当前工作目录

    Returns:
        ProjectPermissions: 项目级权限配置对象
    """
    config_dir = get_project_config_dir(cwd)
    permissions_file = config_dir / "permissions.json"

    if not permissions_file.exists():
        return ProjectPermissions()

    try:
        raw = json.loads(permissions_file.read_text(encoding="utf-8"))
        return ProjectPermissions.model_validate(raw)
    except Exception as exc:
        logger.warning("Failed to load project permissions from %s: %s", permissions_file, exc)
        return ProjectPermissions()
