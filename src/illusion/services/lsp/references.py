"""
LSP 引用查找 — 基于正则的符号引用搜索。
"""

from __future__ import annotations

import re
from pathlib import Path

from illusion.services.lsp.utils import extract_symbol_at_position, iter_python_files


def find_references(
    *,
    root: Path,
    file_path: Path,
    symbol: str | None = None,
    line: int | None = None,
    character: int | None = None,
) -> list[tuple[Path, int, str]]:
    """返回符号的行方向引用。"""
    target = symbol or extract_symbol_at_position(file_path, line=line, character=character)
    if not target:
        return []
    pattern = re.compile(rf"\b{re.escape(target)}\b")
    matches: list[tuple[Path, int, str]] = []
    for candidate in iter_python_files(root):
        for lineno, raw_line in enumerate(candidate.read_text(encoding="utf-8").splitlines(), start=1):
            if pattern.search(raw_line):
                matches.append((candidate, lineno, raw_line.strip()))
    return matches
