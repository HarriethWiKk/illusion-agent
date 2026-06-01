"""
LSP 悬停信息 — 获取符号的文档和签名。
"""

from __future__ import annotations

from pathlib import Path

from illusion.services.lsp.models import SymbolLocation
from illusion.services.lsp.navigation import go_to_definition


def hover(
    *,
    root: Path,
    file_path: Path,
    symbol: str | None = None,
    line: int | None = None,
    character: int | None = None,
) -> SymbolLocation | None:
    """返回符号的最佳悬停目标。"""
    matches = go_to_definition(
        root=root,
        file_path=file_path,
        symbol=symbol,
        line=line,
        character=character,
    )
    return matches[0] if matches else None
