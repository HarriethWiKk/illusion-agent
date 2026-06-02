"""
LSP 代码智能工具
================

与 claude-code 参考项目的 LSP 工具对齐。
支持所有已配置语言的代码智能操作。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from illusion.services.lsp.config import load_lsp_config
from illusion.services.lsp.manager import LspManager
from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult
from illusion.tools.lsp_formatters import (
    format_document_symbol,
    format_find_references,
    format_go_to_definition,
    format_hover,
    format_incoming_calls,
    format_outgoing_calls,
    format_prepare_call_hierarchy,
    format_workspace_symbol,
    resolve_path,
)
from illusion.tools.lsp_schemas import LspToolInput

# 全局 LSP 管理器实例（延迟初始化）
_manager: LspManager | None = None


def _get_manager() -> LspManager:
    """获取或创建全局 LspManager 实例。"""
    global _manager
    if _manager is None:
        from illusion.config.paths import get_config_file_path
        from illusion.config.settings import load_settings

        settings_path = get_config_file_path()
        configs = load_lsp_config(settings_path)
        _manager = LspManager(configs)
    return _manager


class LspTool(BaseTool):
    """LSP 代码智能工具。"""

    name = "lsp"
    description = """Interact with Language Server Protocol (LSP) servers to get code intelligence features.

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

Note: LSP servers must be configured for the file type. If no server is available, an error will be returned."""

    input_model = LspToolInput

    def is_read_only(self, arguments: LspToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: LspToolInput, context: ToolExecutionContext) -> ToolResult:
        manager = _get_manager()
        root = context.cwd.resolve()
        op = arguments.operation

        # workspaceSymbol 不需要 filePath
        if op == "workspaceSymbol":
            return await self._workspace_symbol(manager, root, arguments)

        if not arguments.filePath:
            return ToolResult(output="filePath is required for this operation.", is_error=True)

        file_path = resolve_path(root, arguments.filePath)
        if not file_path.exists():
            return ToolResult(output=f"File not found: {file_path}", is_error=True)

        lang_id = manager.get_language_id(file_path)
        if lang_id is None:
            return ToolResult(
                output=(
                    f"Unsupported file type: {file_path.suffix}. "
                    f"Supported: {', '.join(sorted(manager.supported_extensions))}"
                ),
                is_error=True,
            )

        client = await manager.get_client(file_path)
        if client is None:
            config = manager._configs.get(lang_id)
            install_hint = f"{config.command}" if config else "the LSP server"
            return ToolResult(
                output=(
                    f"No LSP server available for {lang_id}. "
                    f"Please install: {install_hint}"
                ),
                is_error=True,
            )

        # LSP 位置参数（0-based）
        position = {"line": arguments.line - 1, "character": arguments.character - 1}
        text_doc = {"uri": file_path.as_uri()}

        try:
            if op == "goToDefinition":
                return await self._go_to_definition(client, root, text_doc, position)
            elif op == "findReferences":
                return await self._find_references(client, root, text_doc, position)
            elif op == "hover":
                return await self._hover(client, root, text_doc, position)
            elif op == "documentSymbol":
                return await self._document_symbol(client, root, text_doc)
            elif op == "goToImplementation":
                return await self._go_to_implementation(client, root, text_doc, position)
            elif op == "prepareCallHierarchy":
                return await self._prepare_call_hierarchy(client, root, text_doc, position)
            elif op == "incomingCalls":
                return await self._incoming_calls(client, root, text_doc, position)
            elif op == "outgoingCalls":
                return await self._outgoing_calls(client, root, text_doc, position)
            else:
                return ToolResult(output=f"Unknown operation: {op}", is_error=True)
        except TimeoutError:
            return ToolResult(output=f"LSP operation '{op}' timed out.", is_error=True)
        except RuntimeError as e:
            return ToolResult(output=f"LSP error: {e}", is_error=True)

    async def _go_to_definition(self, client: Any, root: Path, text_doc: dict, position: dict) -> ToolResult:
        result = await client.request(
            "textDocument/definition",
            {"textDocument": text_doc, "position": position},
        )
        results = result if isinstance(result, list) else [result] if result else []
        return ToolResult(output=format_go_to_definition(results, root))

    async def _find_references(self, client: Any, root: Path, text_doc: dict, position: dict) -> ToolResult:
        result = await client.request(
            "textDocument/references",
            {
                "textDocument": text_doc,
                "position": position,
                "context": {"includeDeclaration": True},
            },
        )
        return ToolResult(output=format_find_references(result or [], root))

    async def _hover(self, client: Any, root: Path, text_doc: dict, position: dict) -> ToolResult:
        result = await client.request(
            "textDocument/hover",
            {"textDocument": text_doc, "position": position},
        )
        return ToolResult(output=format_hover(result, root))

    async def _document_symbol(self, client: Any, root: Path, text_doc: dict) -> ToolResult:
        result = await client.request(
            "textDocument/documentSymbol",
            {"textDocument": text_doc},
        )
        return ToolResult(output=format_document_symbol(result or [], root))

    async def _workspace_symbol(self, manager: Any, root: Path, arguments: LspToolInput) -> ToolResult:
        all_results: list[dict] = []
        for lang_id in manager._configs:
            client = await manager.get_client_for_language(lang_id)
            if client is None:
                continue
            try:
                result = await client.request("workspace/symbol", {"query": arguments.filePath or ""})
                if result:
                    all_results.extend(result)
            except Exception:
                continue
        return ToolResult(output=format_workspace_symbol(all_results, root))

    async def _go_to_implementation(self, client: Any, root: Path, text_doc: dict, position: dict) -> ToolResult:
        result = await client.request(
            "textDocument/implementation",
            {"textDocument": text_doc, "position": position},
        )
        results = result if isinstance(result, list) else [result] if result else []
        return ToolResult(output=format_go_to_definition(results, root))

    async def _prepare_call_hierarchy(self, client: Any, root: Path, text_doc: dict, position: dict) -> ToolResult:
        result = await client.request(
            "textDocument/prepareCallHierarchy",
            {"textDocument": text_doc, "position": position},
        )
        return ToolResult(output=format_prepare_call_hierarchy(result or [], root))

    async def _incoming_calls(self, client: Any, root: Path, text_doc: dict, position: dict) -> ToolResult:
        items = await client.request(
            "textDocument/prepareCallHierarchy",
            {"textDocument": text_doc, "position": position},
        )
        if not items:
            return ToolResult(output="No incoming calls found (nothing calls this function).")
        item = items[0] if isinstance(items, list) else items
        result = await client.request("callHierarchy/incomingCalls", {"item": item})
        return ToolResult(output=format_incoming_calls(result or [], root))

    async def _outgoing_calls(self, client: Any, root: Path, text_doc: dict, position: dict) -> ToolResult:
        items = await client.request(
            "textDocument/prepareCallHierarchy",
            {"textDocument": text_doc, "position": position},
        )
        if not items:
            return ToolResult(output="No outgoing calls found (this function calls nothing).")
        item = items[0] if isinstance(items, list) else items
        result = await client.request("callHierarchy/outgoingCalls", {"item": item})
        return ToolResult(output=format_outgoing_calls(result or [], root))
