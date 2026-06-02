"""
LSP 工具输入 Schema
===================

与 claude-code 参考项目的 LSP 工具 schema 保持一致。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LspToolInput(BaseModel):
    """LSP 工具输入参数。"""

    operation: Literal[
        "goToDefinition",
        "findReferences",
        "hover",
        "documentSymbol",
        "workspaceSymbol",
        "goToImplementation",
        "prepareCallHierarchy",
        "incomingCalls",
        "outgoingCalls",
    ] = Field(description="The LSP operation to perform")

    filePath: str = Field(
        default="",
        description="The absolute or relative path to the file",
    )

    line: int = Field(
        default=0,
        description="The line number (1-based, as shown in editors)",
        ge=0,
    )

    character: int = Field(
        default=0,
        description="The character offset (1-based, as shown in editors)",
        ge=0,
    )
