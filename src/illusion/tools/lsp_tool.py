"""
轻量级代码智能工具
==================

本模块提供基于 AST 的代码智能查询功能，用于 Python 代码的定义、引用、符号搜索等。

主要组件：
    - LspTool: 代码智能查询工具

使用示例：
    >>> from illusion.tools import LspTool
    >>> tool = LspTool()
"""

from __future__ import annotations

from pathlib import Path

from illusion.services.lsp import (
    AstCache,
    FileChangeNotifier,
    find_references,
    go_to_definition,
    go_to_implementation,
    hover,
    incoming_calls,
    list_document_symbols,
    outgoing_calls,
    prepare_call_hierarchy,
    workspace_symbol_search,
)
from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult
from illusion.tools.lsp_formatters import (
    display_path,
    format_hierarchy_item,
    format_incoming_calls,
    format_outgoing_calls,
    format_references,
    format_symbol_locations,
    resolve_path,
)
from illusion.tools.lsp_schemas import LspToolInput

# 全局缓存实例
_ast_cache = AstCache()
_file_notifier = FileChangeNotifier(_ast_cache)


class LspTool(BaseTool):
    """Python 源文件的只读代码智能（基于 AST 分析）。

    用于查询代码定义、引用、悬停信息、调用层次等。
    """

    name = "lsp"
    description = """Interact with code intelligence features for Python source files.

Supported operations:
- goToDefinition: Find where a symbol is defined
- findReferences: Find all references to a symbol
- hover: Get hover information (documentation, type info) for a symbol
- documentSymbol: Get all symbols (functions, classes, variables) in a document
- workspaceSymbol: Search for symbols across the entire workspace
- goToImplementation: Find implementations of an interface or abstract method
- prepareCallHierarchy: Get call hierarchy item at a position (functions/methods)
- incomingCalls: Find all functions/methods that call the function at a position
- outgoingCalls: Find all functions/methods called by the function at a position

All operations require:
- filePath: The file to operate on
- line: The line number (1-based, as shown in editors)
- character: The character offset (1-based, as shown in editors)

Note: This tool uses AST analysis for Python files. No external language server is required."""
    input_model = LspToolInput

    def is_read_only(self, arguments: LspToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: LspToolInput, context: ToolExecutionContext) -> ToolResult:
        root = context.cwd.resolve()

        # workspace_symbol 操作 — 不需要 file_path
        if arguments.operation == "workspace_symbol":
            results = workspace_symbol_search(root, arguments.query or "")
            return ToolResult(output=format_symbol_locations(results, root))

        # 解析文件路径
        assert arguments.file_path is not None
        file_path = resolve_path(root, arguments.file_path)
        if not file_path.exists():
            return ToolResult(output=f"File not found: {file_path}", is_error=True)
        if file_path.suffix != ".py":
            return ToolResult(output="The lsp tool currently supports Python files only.", is_error=True)

        # document_symbol
        if arguments.operation == "document_symbol":
            return ToolResult(output=format_symbol_locations(list_document_symbols(file_path), root))

        # go_to_definition
        if arguments.operation == "go_to_definition":
            results = go_to_definition(
                root=root, file_path=file_path,
                symbol=arguments.symbol, line=arguments.line, character=arguments.character,
            )
            return ToolResult(output=format_symbol_locations(results, root))

        # find_references
        if arguments.operation == "find_references":
            results = find_references(
                root=root, file_path=file_path,
                symbol=arguments.symbol, line=arguments.line, character=arguments.character,
            )
            return ToolResult(output=format_references(results, root))

        # hover
        if arguments.operation == "hover":
            result = hover(
                root=root, file_path=file_path,
                symbol=arguments.symbol, line=arguments.line, character=arguments.character,
            )
            if result is None:
                return ToolResult(output="No hover information available.")
            parts = [
                f"{result.kind} {result.name}",
                f"path: {display_path(result.path, root)}:{result.line}:{result.character}",
            ]
            if result.signature:
                parts.append(f"signature: {result.signature}")
            if result.docstring:
                parts.append(f"docstring: {result.docstring.strip()}")
            return ToolResult(output="\n".join(parts))

        # go_to_implementation
        if arguments.operation == "go_to_implementation":
            results = go_to_implementation(
                root=root, file_path=file_path,
                symbol=arguments.symbol, line=arguments.line, character=arguments.character,
            )
            return ToolResult(output=format_symbol_locations(results, root))

        # prepare_call_hierarchy
        if arguments.operation == "prepare_call_hierarchy":
            result = prepare_call_hierarchy(
                root=root, file_path=file_path,
                symbol=arguments.symbol, line=arguments.line, character=arguments.character,
            )
            if result is None:
                return ToolResult(output="(no call hierarchy item)")
            return ToolResult(output=format_hierarchy_item(result, root))

        # incoming_calls
        if arguments.operation == "incoming_calls":
            results = incoming_calls(
                root=root, file_path=file_path,
                symbol=arguments.symbol, line=arguments.line, character=arguments.character,
            )
            return ToolResult(output=format_incoming_calls(results, root))

        # outgoing_calls
        if arguments.operation == "outgoing_calls":
            results = outgoing_calls(
                root=root, file_path=file_path,
                symbol=arguments.symbol, line=arguments.line, character=arguments.character,
            )
            return ToolResult(output=format_outgoing_calls(results, root))

        return ToolResult(output=f"Unknown operation: {arguments.operation}", is_error=True)
