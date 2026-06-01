"""
LSP 符号收集与搜索。

提供文档符号列表和工作区符号搜索功能。
"""

from __future__ import annotations

import ast
from pathlib import Path

from illusion.services.lsp.models import SymbolLocation
from illusion.services.lsp.utils import iter_python_files


def list_document_symbols(path: Path) -> list[SymbolLocation]:
    """从 Python 源文件中返回顶层和嵌套符号。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    symbols: list[SymbolLocation] = []
    _collect_symbols(tree, path, symbols, parent=None)
    return symbols


def workspace_symbol_search(root: Path, query: str) -> list[SymbolLocation]:
    """返回名称包含 query 的符号。"""
    needle = query.lower().strip()
    if not needle:
        return []
    matches: list[SymbolLocation] = []
    for file_path in iter_python_files(root):
        for symbol in list_document_symbols(file_path):
            if needle in symbol.name.lower():
                matches.append(symbol)
    return matches


def _collect_symbols(
    node: ast.AST,
    path: Path,
    bucket: list[SymbolLocation],
    *,
    parent: str | None,
) -> None:
    """递归收集 AST 中的符号。"""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = f"{parent}.{child.name}" if parent else child.name
            args = [arg.arg for arg in child.args.args]
            signature = f"def {child.name}({', '.join(args)})"
            bucket.append(
                SymbolLocation(
                    name=name,
                    kind="function",
                    path=path,
                    line=child.lineno,
                    character=child.col_offset + 1,
                    signature=signature,
                    docstring=ast.get_docstring(child) or "",
                )
            )
            _collect_symbols(child, path, bucket, parent=name)
        elif isinstance(child, ast.ClassDef):
            name = f"{parent}.{child.name}" if parent else child.name
            bucket.append(
                SymbolLocation(
                    name=name,
                    kind="class",
                    path=path,
                    line=child.lineno,
                    character=child.col_offset + 1,
                    signature=f"class {child.name}",
                    docstring=ast.get_docstring(child) or "",
                )
            )
            _collect_symbols(child, path, bucket, parent=name)
        elif isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    name = f"{parent}.{target.id}" if parent else target.id
                    bucket.append(
                        SymbolLocation(
                            name=name,
                            kind="variable",
                            path=path,
                            line=target.lineno,
                            character=target.col_offset + 1,
                            signature=f"{target.id} = ...",
                        )
                    )
        else:
            _collect_symbols(child, path, bucket, parent=parent)
