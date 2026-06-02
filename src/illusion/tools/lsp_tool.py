"""
LSP 代码智能工具
================

与 claude-code 参考项目的 LSP 工具对齐。
支持所有已配置语言的代码智能操作。
"""

from __future__ import annotations

import asyncio
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
# 跟踪已打开的文件 URI -> language_id
_opened_files: dict[str, str] = {}


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
- workspaceSymbol: Search for symbols across the entire workspace (requires 'query' parameter)
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

    @staticmethod
    def _find_workspace_root(file_path: Path, cwd: Path) -> Path:
        """查找文件的工作区根目录。

        按优先级尝试：
        1. 向上查找包含 .git 的目录
        2. 向上查找包含 pyproject.toml/package.json/go.mod/Cargo.toml 的目录
        3. 使用 cwd
        """
        current = file_path.parent
        for marker in (".git", "pyproject.toml", "package.json", "go.mod", "Cargo.toml"):
            check = current
            while check != check.parent:
                if (check / marker).exists():
                    return check
                check = check.parent
        return cwd

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

        # 初始化 LSP 服务器（使用文件所在目录的最近父目录作为工作区根目录）
        if not client.is_initialized:
            workspace_root = self._find_workspace_root(file_path, root)
            await manager.initialize_client(
                lang_id,
                workspace_root.as_uri(),
                root_path=str(workspace_root),
            )

        # LSP 位置参数（0-based）
        position = {"line": arguments.line - 1, "character": arguments.character - 1}
        text_doc = {"uri": file_path.as_uri()}

        # 通知 LSP 服务器文件已打开（仅首次）
        file_uri = text_doc["uri"]
        if _opened_files.get(file_uri) != lang_id:
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")

                # 设置诊断等待事件
                diag_event = asyncio.Event()
                def _on_diag(params: dict) -> None:
                    if params.get("uri") == file_uri:
                        diag_event.set()
                client.on_notification("textDocument/publishDiagnostics", _on_diag)

                await client.notify("textDocument/didOpen", {
                    "textDocument": {
                        "uri": file_uri,
                        "languageId": lang_id,
                        "version": 1,
                        "text": content,
                    },
                })
                _opened_files[file_uri] = lang_id

                # 等待服务器分析完成（publishDiagnostics 通知），最长 10 秒
                try:
                    await asyncio.wait_for(diag_event.wait(), timeout=10)
                except asyncio.TimeoutError:
                    pass  # 超时后继续尝试
            except Exception:
                pass  # 非致命错误

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
            msg = str(e)
            if "Unhandled method" in msg:
                return ToolResult(
                    output=f"The LSP server for {lang_id} does not support the '{op}' operation.",
                    is_error=True,
                )
            return ToolResult(output=f"LSP error: {msg}", is_error=True)

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
        query = arguments.query or arguments.filePath or ""
        if not query:
            return ToolResult(
                output="workspaceSymbol requires a query. Use the 'query' parameter.",
                is_error=True,
            )

        all_results: list[dict] = []
        for lang_id in manager._configs:
            client = await manager.get_client_for_language(lang_id)
            if client is None:
                continue

            if not client.is_initialized:
                await manager.initialize_client(lang_id, root.as_uri(), root_path=str(root))

            # 确保至少打开过一个文件以触发工作区索引
            if lang_id not in _opened_files.values():
                await self._open_first_file(client, lang_id, root)

            # 用 documentSymbol 作为"探针"确认服务器就绪
            # 如果探针失败，说明服务器还在索引，等待后重试
            probe_uri = next((uri for uri, lid in _opened_files.items() if lid == lang_id), None)
            if probe_uri:
                for attempt in range(3):
                    try:
                        probe = await client.request(
                            "textDocument/documentSymbol",
                            {"textDocument": {"uri": probe_uri}},
                            timeout=10,
                        )
                        if probe is not None:
                            break  # 服务器就绪
                    except Exception:
                        pass
                    await asyncio.sleep(2)  # 等待索引

            # 发送 workspace/symbol 请求
            try:
                result = await client.request("workspace/symbol", {"query": query}, timeout=15)
                if result:
                    interesting_kinds = {5, 6, 11, 12, 13, 14, 23, 10}
                    filtered = [s for s in result if s.get("kind", 0) in interesting_kinds]
                    all_results.extend(filtered[:10])
            except Exception:
                continue

        return ToolResult(output=format_workspace_symbol(all_results, root))

    @staticmethod
    async def _open_first_file(client: Any, lang_id: str, root: Path) -> None:
        """打开工作区中的一个源文件，等待索引完成。优先查找常见目录。"""
        ext_map = {".py": "python", ".ts": "typescript", ".go": "go", ".rs": "rust", ".c": "cpp"}
        target_ext = None
        for ext, lid in ext_map.items():
            if lid == lang_id:
                target_ext = ext
                break
        if not target_ext:
            return

        # 优先查找常见源码目录，避免 rglob 全盘搜索
        search_dirs = [root / "src", root / "lib", root / "app", root]
        target_file = None
        for search_dir in search_dirs:
            if not search_dir.is_dir():
                continue
            try:
                for f in search_dir.iterdir():
                    if f.is_file() and f.suffix == target_ext:
                        target_file = f
                        break
                    if f.is_dir() and not f.name.startswith(".") and f.name not in ("node_modules", "__pycache__", "venv", ".venv"):
                        for sub in f.iterdir():
                            if sub.is_file() and sub.suffix == target_ext:
                                target_file = sub
                                break
                        if target_file:
                            break
            except OSError:
                continue
            if target_file:
                break

        if not target_file:
            return

        try:
            content = target_file.read_text(encoding="utf-8", errors="replace")
            file_uri = target_file.as_uri()

            # 等待诊断通知
            diag_event = asyncio.Event()
            def _on_diag(params: dict) -> None:
                if params.get("uri") == file_uri:
                    diag_event.set()
            client.on_notification("textDocument/publishDiagnostics", _on_diag)

            await client.notify("textDocument/didOpen", {
                "textDocument": {
                    "uri": file_uri, "languageId": lang_id, "version": 1, "text": content,
                },
            })
            _opened_files[file_uri] = lang_id

            try:
                await asyncio.wait_for(diag_event.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass
        except Exception:
            pass

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
