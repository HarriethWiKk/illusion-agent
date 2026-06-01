"""
轻量级代码智能辅助模块 — 用于 LSP 工具
====================================

本模块实现轻量级代码智能功能，比完整的语言服务器集成更小。
为 Python 源文件提供稳定的只读操作，使模型能够执行类似 Claude Code 工作流程中的定义、引用、悬停和符号查询。

主要功能：
    - 列出文档符号
    - 工作区符号搜索
    - 跳转到定义
    - 查找引用
    - 悬停信息

类说明：
    - SymbolLocation: 符号位置数据类
    - list_document_symbols: 列出文档符号
    - workspace_symbol_search: 工作区符号搜索
    - go_to_definition: 跳转到定义
    - find_references: 查找引用
    - hover: 悬停信息

使用示例：
    >>> from illusion.services.lsp import list_document_symbols, go_to_definition
    >>> # 列出文件中的符号
    >>> symbols = list_document_symbols(Path("src/main.py"))
    >>> # 跳转到定义
    >>> defs = go_to_definition(root=Path("."), file_path=Path("src/main.py"), symbol="my_function")
"""

from illusion.services.lsp.cache import AstCache, FileChangeNotifier
from illusion.services.lsp.call_hierarchy import incoming_calls, outgoing_calls, prepare_call_hierarchy
from illusion.services.lsp.diagnostics import Diagnostic, DiagnosticRegistry
from illusion.services.lsp.hover import hover
from illusion.services.lsp.models import SymbolLocation
from illusion.services.lsp.navigation import go_to_definition, go_to_implementation
from illusion.services.lsp.references import find_references
from illusion.services.lsp.symbols import list_document_symbols, workspace_symbol_search
from illusion.services.lsp.utils import extract_symbol_at_position, iter_python_files

__all__ = [
    "AstCache",
    "Diagnostic",
    "DiagnosticRegistry",
    "FileChangeNotifier",
    "SymbolLocation",
    "extract_symbol_at_position",
    "find_references",
    "go_to_definition",
    "go_to_implementation",
    "hover",
    "incoming_calls",
    "iter_python_files",
    "list_document_symbols",
    "outgoing_calls",
    "prepare_call_hierarchy",
    "workspace_symbol_search",
]
