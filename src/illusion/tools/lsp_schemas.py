"""
LSP 工具输入模型与操作名映射。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# 驼峰 → 蛇形操作名映射（兼容两种命名风格）
_OP_CAMEL_TO_SNAKE: dict[str, str] = {
    "goToDefinition": "go_to_definition",
    "findReferences": "find_references",
    "documentSymbol": "document_symbol",
    "workspaceSymbol": "workspace_symbol",
    "goToImplementation": "go_to_implementation",
    "prepareCallHierarchy": "prepare_call_hierarchy",
    "incomingCalls": "incoming_calls",
    "outgoingCalls": "outgoing_calls",
}


class LspToolInput(BaseModel):
    """代码智能查询参数。

    属性：
        operation: 要执行的代码智能操作（支持驼峰和蛇形两种命名）
        file_path: 用于基于文件的操作的源文件路径
        symbol: 要查找的显式符号名称
        line: 基于位置查询的 1-based 行号
        character: 基于位置查询的 1-based 字符偏移
        query: workspace_symbol 的子字符串查询
    """

    operation: Literal[
        "document_symbol",
        "workspace_symbol",
        "go_to_definition",
        "find_references",
        "hover",
        "go_to_implementation",
        "prepare_call_hierarchy",
        "incoming_calls",
        "outgoing_calls",
    ] = Field(description="The code intelligence operation to perform")
    file_path: str | None = Field(default=None, description="Path to the source file for file-based operations")
    symbol: str | None = Field(default=None, description="Explicit symbol name to look up")
    line: int | None = Field(default=None, ge=1, description="The line number (1-based, as shown in editors)")
    character: int | None = Field(default=None, ge=1, description="The character offset (1-based, as shown in editors)")
    query: str | None = Field(default=None, description="Substring query for workspace_symbol")

    @model_validator(mode="before")
    @classmethod
    def normalize_operation(cls, data: Any) -> Any:
        """将驼峰操作名映射为蛇形。"""
        if isinstance(data, dict) and "operation" in data:
            op: str = data["operation"]
            if op in _OP_CAMEL_TO_SNAKE:
                data["operation"] = _OP_CAMEL_TO_SNAKE[op]
        return data

    @model_validator(mode="after")
    def validate_arguments(self) -> "LspToolInput":
        # workspace_symbol 需要 query 参数
        if self.operation == "workspace_symbol":
            if not self.query:
                raise ValueError("workspace_symbol requires query")
            return self
        # 其他操作需要 file_path
        if not self.file_path:
            raise ValueError(f"{self.operation} requires file_path")
        # document_symbol 不需要 symbol 或 line
        if self.operation == "document_symbol":
            return self
        # 其余操作需要 symbol 或 line
        if not self.symbol and self.line is None:
            raise ValueError(f"{self.operation} requires symbol or line")
        return self
