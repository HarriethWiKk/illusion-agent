"""
插件清单模式模块
================

定义插件清单的数据模型，对齐 Claude Code PluginManifestSchema。
"""

from __future__ import annotations

from pydantic import BaseModel


class PluginManifest(BaseModel):
    """插件清单，对齐 Claude Code PluginManifestSchema。"""

    name: str
    version: str = "0.0.0"
    description: str = ""
    enabled_by_default: bool = True
    skills_dir: str = "skills"
    hooks_file: str = "hooks.json"
    mcp_file: str = "mcp.json"
    author: dict | None = None
    commands: str | list | dict | None = None
    agents: str | list | None = None
    skills: str | list | None = None
    hooks: str | dict | list | None = None
    # 对齐 Claude Code
    output_styles: str | list | None = None
    settings: dict | None = None
    user_config: dict | None = None
