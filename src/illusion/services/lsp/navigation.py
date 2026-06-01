"""
LSP 导航操作 — 定义跳转与实现查找。
"""

from __future__ import annotations

import ast
from pathlib import Path

from illusion.services.lsp.models import SymbolLocation
from illusion.services.lsp.symbols import list_document_symbols
from illusion.services.lsp.utils import _get_ast_name, extract_symbol_at_position, iter_python_files


def go_to_definition(
    *,
    root: Path,
    file_path: Path,
    symbol: str | None = None,
    line: int | None = None,
    character: int | None = None,
) -> list[SymbolLocation]:
    """解析符号的可能定义。"""
    target = symbol or extract_symbol_at_position(file_path, line=line, character=character)
    if not target:
        return []
    matches: list[SymbolLocation] = []
    for candidate in iter_python_files(root):
        for item in list_document_symbols(candidate):
            if item.name == target:
                matches.append(item)
    return matches


def go_to_implementation(
    *,
    root: Path,
    file_path: Path,
    symbol: str | None = None,
    line: int | None = None,
    character: int | None = None,
) -> list[SymbolLocation]:
    """查找类或方法的子类实现。

    对于类：查找继承该类的子类。
    对于方法：查找子类中重写该方法的位置。
    """
    target = symbol or extract_symbol_at_position(file_path, line=line, character=character)
    if not target:
        return []

    is_method = "." in target
    base_class = target.split(".")[0] if is_method else target
    method_name = target.split(".")[-1] if is_method else None

    matches: list[SymbolLocation] = []
    for candidate in iter_python_files(root):
        tree = ast.parse(candidate.read_text(encoding="utf-8"), filename=str(candidate))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = _get_ast_name(base)
                    if base_name and (base_name == base_class or base_name.endswith(f".{base_class}")):
                        if method_name:
                            for child in ast.iter_child_nodes(node):
                                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                                    matches.append(SymbolLocation(
                                        name=f"{node.name}.{child.name}",
                                        kind="method",
                                        path=candidate,
                                        line=child.lineno,
                                        character=child.col_offset + 1,
                                        signature=f"def {child.name}(...)",
                                        docstring=ast.get_docstring(child) or "",
                                    ))
                        else:
                            matches.append(SymbolLocation(
                                name=node.name,
                                kind="class",
                                path=candidate,
                                line=node.lineno,
                                character=node.col_offset + 1,
                                signature=f"class {node.name}",
                                docstring=ast.get_docstring(node) or "",
                            ))
    return matches
