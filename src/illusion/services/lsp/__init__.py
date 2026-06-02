"""
LSP 服务模块
============

提供统一的 LSP 客户端和多语言代码智能支持。
"""

from illusion.services.lsp.client import LspClient
from illusion.services.lsp.config import LspServerConfig, load_lsp_config
from illusion.services.lsp.manager import LspManager
from illusion.services.lsp.types import ModuleInfo, SymbolInfo, SymbolKind

__all__ = [
    "LspClient",
    "LspManager",
    "LspServerConfig",
    "ModuleInfo",
    "SymbolInfo",
    "SymbolKind",
    "load_lsp_config",
]
