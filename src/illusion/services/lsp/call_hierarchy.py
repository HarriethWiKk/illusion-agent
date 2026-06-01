"""
LSP 调用层次分析 — 准备调用层次、入向/出向调用查找。
"""

from __future__ import annotations

import ast
from pathlib import Path

from illusion.services.lsp.models import SymbolLocation
from illusion.services.lsp.navigation import go_to_definition
from illusion.services.lsp.utils import (
    _find_enclosing_def,
    _find_func_node,
    _get_ast_name,
    _get_source_line,
    extract_symbol_at_position,
    iter_python_files,
)


def prepare_call_hierarchy(
    *,
    root: Path,
    file_path: Path,
    symbol: str | None = None,
    line: int | None = None,
    character: int | None = None,
) -> SymbolLocation | None:
    """获取指定位置的调用层次节点。"""
    target = symbol or extract_symbol_at_position(file_path, line=line, character=character)
    if not target:
        return None
    matches = go_to_definition(root=root, file_path=file_path, symbol=target)
    return matches[0] if matches else None


def incoming_calls(
    *,
    root: Path,
    file_path: Path,
    symbol: str | None = None,
    line: int | None = None,
    character: int | None = None,
) -> list[tuple[Path, int, str, str]]:
    """查找所有调用指定函数/方法的位置。

    返回 (调用文件, 行号, 调用者函数名, 行文本) 列表。
    """
    target = symbol or extract_symbol_at_position(file_path, line=line, character=character)
    if not target:
        return []

    call_name = target.split(".")[-1]

    results: list[tuple[Path, int, str, str]] = []
    for candidate in iter_python_files(root):
        try:
            tree = ast.parse(candidate.read_text(encoding="utf-8"), filename=str(candidate))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                callee = _get_ast_name(node.func)
                if callee == target or callee == call_name:
                    caller = _find_enclosing_def(tree, node.lineno)
                    results.append((candidate, node.lineno, caller or "(module level)", _get_source_line(candidate, node.lineno)))
    return results


def outgoing_calls(
    *,
    root: Path,
    file_path: Path,
    symbol: str | None = None,
    line: int | None = None,
    character: int | None = None,
) -> list[tuple[str, Path, int]]:
    """查找指定函数/方法内部调用的所有函数。

    返回 (被调用名, 定义文件, 行号) 列表。
    """
    target = symbol or extract_symbol_at_position(file_path, line=line, character=character)
    if not target:
        return []

    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    func_node = _find_func_node(tree, target)
    if func_node is None:
        return []

    seen: set[str] = set()
    results: list[tuple[str, Path, int]] = []
    for node in ast.walk(func_node):
        if node is func_node:
            continue
        if isinstance(node, ast.Call):
            callee = _get_ast_name(node.func)
            if callee and callee not in seen:
                seen.add(callee)
                defs = go_to_definition(root=root, file_path=file_path, symbol=callee)
                if defs:
                    results.append((callee, defs[0].path, defs[0].line))
                else:
                    results.append((callee, Path(), 0))

    return results
