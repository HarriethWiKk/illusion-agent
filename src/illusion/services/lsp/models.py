"""
LSP 数据模型与全局常量。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# Python 文件模式
_PYTHON_GLOB = "*.py"
# 跳过的目录
_SKIP_PARTS = {".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "node_modules"}


@dataclass(frozen=True)
class SymbolLocation:
    """工作区内的解析符号位置。"""

    name: str
    kind: str
    path: Path
    line: int
    character: int
    signature: str = ""
    docstring: str = ""
