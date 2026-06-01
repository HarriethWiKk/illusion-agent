"""
LSP 共享工具函数。

提供 AST 辅助函数、文件遍历（含 Gitignore 过滤）、位置提取等基础功能。
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

from illusion.services.lsp.models import _PYTHON_GLOB, _SKIP_PARTS


def iter_python_files(root: Path, *, use_gitignore: bool = True) -> list[Path]:
    """按稳定顺序返回 Python 源文件列表，支持 Gitignore 过滤。"""
    files: list[Path] = []
    for path in root.rglob(_PYTHON_GLOB):
        if any(part in _SKIP_PARTS for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    files.sort()

    if use_gitignore and files:
        files = _filter_gitignored(files, root)

    return files


def _filter_gitignored(files: list[Path], root: Path) -> list[Path]:
    """批量调用 git check-ignore 过滤被 gitignore 的文件。"""
    try:
        # 检查是否在 git 仓库中
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=root,
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return files

    ignored: set[Path] = set()
    batch_size = 50
    for i in range(0, len(files), batch_size):
        batch = files[i : i + batch_size]
        try:
            result = subprocess.run(
                ["git", "check-ignore", *[str(f) for f in batch]],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.splitlines():
                    trimmed = line.strip()
                    if trimmed:
                        ignored.add(Path(trimmed).resolve())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    if not ignored:
        return files

    return [f for f in files if f.resolve() not in ignored]


def extract_symbol_at_position(
    file_path: Path,
    *,
    line: int | None,
    character: int | None,
) -> str | None:
    """从 1 基数的行/字符位置提取可能的标识符。"""
    if line is None:
        return None
    lines = file_path.read_text(encoding="utf-8").splitlines()
    if line < 1 or line > len(lines):
        return None
    text = lines[line - 1]
    if not text:
        return None
    index = max(0, min((character or 1) - 1, len(text) - 1))
    for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", text):
        if match.start() <= index < match.end():
            return match.group(0)
    for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", text):
        return match.group(0)
    return None


def _get_ast_name(node: ast.AST) -> str | None:
    """从 AST 节点提取名称字符串（支持 a.b.c 形式的属性访问）。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        inner = _get_ast_name(node.value)
        if inner is not None:
            return f"{inner}.{node.attr}"
        return node.attr
    return None


def _find_enclosing_def(tree: ast.AST, lineno: int) -> str | None:
    """按行号查找所在的函数/类定义名。"""
    best: str | None = None
    best_end: int = -1
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            end = node.end_lineno or node.lineno
            if node.lineno <= lineno <= end and end > best_end:
                best_end = end
                best = node.name
    return best


def _find_func_node(tree: ast.AST, target: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """在 AST 树中按名称或 ClassName.method 形式查找函数节点。"""
    parts = target.split(".")
    func_name = parts[-1]
    class_name = parts[0] if len(parts) >= 2 else None

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                if class_name:
                    for parent in ast.walk(tree):
                        if isinstance(parent, ast.ClassDef) and parent.name == class_name:
                            for child in ast.walk(parent):
                                if child is node:
                                    return node
                else:
                    return node
    return None


def _get_source_line(file_path: Path, lineno: int) -> str:
    """读取文件指定行的文本。"""
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
        if 1 <= lineno <= len(lines):
            return lines[lineno - 1].strip()
    except OSError:
        pass
    return ""
