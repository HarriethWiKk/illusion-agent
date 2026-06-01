"""
LSP 结果格式化函数。

将各种 LSP 操作的原始结果转换为人类可读的文本格式。
"""

from __future__ import annotations

from pathlib import Path


def resolve_path(base: Path, candidate: str) -> Path:
    """解析相对路径为绝对路径。"""
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def display_path(path: Path, root: Path) -> str:
    """将路径显示为相对于根目录的路径。"""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def format_symbol_locations(results: list, root: Path) -> str:
    """格式化符号位置结果。"""
    if not results:
        return "(no results)"
    lines = [f"Found {len(results)} symbol(s):"]
    for item in results:
        lines.append(
            f"  {item.kind} {item.name} - {display_path(item.path, root)}:{item.line}:{item.character}"
        )
        if item.signature:
            lines.append(f"    signature: {item.signature}")
        if item.docstring:
            lines.append(f"    docstring: {item.docstring.strip()}")
    return "\n".join(lines)


def format_references(results: list[tuple[Path, int, str]], root: Path) -> str:
    """格式化引用结果，按文件分组。"""
    if not results:
        return "No references found. This may occur if the symbol has no usages."

    # 按文件分组
    by_file: dict[str, list[tuple[int, str]]] = {}
    for path, line, text in results:
        fp = display_path(path, root)
        by_file.setdefault(fp, []).append((line, text))

    lines = [f"Found {len(results)} references across {len(by_file)} file(s):"]
    for fp, locations in by_file.items():
        lines.append(f"\n{fp}:")
        for line, text in locations:
            lines.append(f"  Line {line}: {text}")
    return "\n".join(lines)


def format_hierarchy_item(item, root: Path) -> str:
    """格式化调用层次项。"""
    parts = [
        f"{item.kind} {item.name}",
        f"path: {display_path(item.path, root)}:{item.line}:{item.character}",
    ]
    if item.signature:
        parts.append(f"signature: {item.signature}")
    if item.docstring:
        parts.append(f"docstring: {item.docstring.strip()}")
    return "\n".join(parts)


def format_incoming_calls(results: list[tuple[Path, int, str, str]], root: Path) -> str:
    """格式化入向调用结果。"""
    if not results:
        return "No incoming calls found (nothing calls this function)."
    lines = [f"Found {len(results)} incoming call(s):"]
    for path, line, caller, text in results:
        lines.append(f"  {display_path(path, root)}:{line} [{caller}] {text}")
    return "\n".join(lines)


def format_outgoing_calls(results: list[tuple[str, Path, int]], root: Path) -> str:
    """格式化出向调用结果。"""
    if not results:
        return "No outgoing calls found (this function calls nothing)."
    lines = [f"Found {len(results)} outgoing call(s):"]
    for name, path, line in results:
        if path != Path() and line > 0:
            lines.append(f"  {name} -> {display_path(path, root)}:{line}")
        else:
            lines.append(f"  {name} -> (definition not found)")
    return "\n".join(lines)
