"""
关键模块识别器
==============

识别项目中的核心模块：入口点、被最多导入的模块、包含最多类/函数的模块等。
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from illusion.commands.init.types import ModuleSummary, ProjectData


def identify_key_modules(data: ProjectData) -> list[ModuleSummary]:
    """识别关键模块

    Args:
        data: 提取阶段的项目数据

    Returns:
        关键模块摘要列表（最多 10 个）
    """
    candidates: list[ModuleSummary] = []

    # Python 模块分析
    if data.python_modules:
        candidates.extend(_analyze_python_modules(data))

    # JS/TS 模块分析
    candidates.extend(_analyze_js_ts_modules(data))

    # Go 入口点
    candidates.extend(_analyze_go_modules(data))

    # 去重并限制数量
    seen_paths: set[str] = set()
    unique: list[ModuleSummary] = []
    for mod in candidates:
        if mod.path not in seen_paths:
            seen_paths.add(mod.path)
            unique.append(mod)

    return unique[:10]


def _analyze_python_modules(data: ProjectData) -> list[ModuleSummary]:
    """分析 Python 模块，识别关键模块"""
    summaries: list[ModuleSummary] = []

    # 计算每个模块的 import 被引用次数
    import_counts: Counter[str] = Counter()
    module_names: dict[str, str] = {}  # name -> path

    for mod in data.python_modules:
        name = _get_module_name(mod.path)
        module_names[name] = str(mod.path)

    for mod in data.python_modules:
        for imp in mod.imports:
            for name in module_names:
                if imp == name or imp.endswith(f".{name}"):
                    import_counts[name] += 1

    # 入口点检测
    for mod in data.python_modules:
        name = _get_module_name(mod.path)

        # CLI 入口点（pyproject scripts）
        is_cli_entry = False
        if data.pyproject_data:
            scripts = data.pyproject_data.get("project", {}).get("scripts", {})
            poetry_scripts = data.pyproject_data.get("tool", {}).get("poetry", {}).get("scripts", {})
            all_scripts = {**scripts, **poetry_scripts}
            for script_path in all_scripts.values():
                if isinstance(script_path, str) and name in script_path:
                    is_cli_entry = True
                    break

        # if __name__ == "__main__" 检测
        has_main = any(
            "if __name__" in (func.docstring or "")
            for func in mod.functions
        )
        # 简单检查：文件中是否有 if __name__ == "__main__"
        if not has_main:
            try:
                content = mod.path.read_text(encoding="utf-8", errors="replace")
                has_main = 'if __name__ == "__main__"' in content
            except OSError:
                pass

        is_entry = is_cli_entry or has_main

        # 核心模块（被多次导入）
        import_count = import_counts.get(name, 0)
        is_core = import_count >= 2

        # 包含较多类/函数的模块
        is_rich = len(mod.classes) >= 3 or len(mod.functions) >= 5

        if is_entry or is_core or is_rich:
            description_parts = []
            if is_entry:
                description_parts.append("entry point")
            if is_core:
                description_parts.append(f"imported by {import_count} modules")
            if is_rich:
                description_parts.append(f"{len(mod.classes)} classes, {len(mod.functions)} functions")

            # 使用模块 docstring 的第一句作为描述
            desc = ""
            if mod.docstring:
                first_line = mod.docstring.split("\n")[0].strip()
                if len(first_line) > 100:
                    first_line = first_line[:97] + "..."
                desc = first_line

            if not desc:
                desc = "; ".join(description_parts) if description_parts else "source module"

            summaries.append(ModuleSummary(
                name=name,
                path=str(mod.path),
                description=desc,
                key_classes=[cls.name for cls in mod.classes[:3]],
                key_functions=[func.name for func in mod.functions[:3]],
            ))

    # 按重要性排序：入口点 > 核心模块 > 丰富模块
    def _sort_key(m: ModuleSummary) -> tuple[int, int]:
        is_entry = 1 if "entry point" in m.description else 0
        score = len(m.key_classes) + len(m.key_functions)
        return (-is_entry, -score)

    summaries.sort(key=_sort_key)
    return summaries[:8]


def _analyze_js_ts_modules(data: ProjectData) -> list[ModuleSummary]:
    """分析 JS/TS 模块"""
    summaries: list[ModuleSummary] = []

    for f in data.files:
        if f.language not in ("JavaScript", "TypeScript", "React"):
            continue

        name = f.path.stem
        path_str = str(f.path)

        # index 文件通常是入口
        if name in ("index", "main", "app"):
            summaries.append(ModuleSummary(
                name=name,
                path=path_str,
                description="entry point",
                key_classes=[],
                key_functions=[],
            ))

    return summaries[:3]


def _analyze_go_modules(data: ProjectData) -> list[ModuleSummary]:
    """分析 Go 模块"""
    summaries: list[ModuleSummary] = []

    for f in data.files:
        if f.language != "Go":
            continue

        path_str = str(f.path)

        # main.go 是入口点
        if f.path.name == "main.go":
            summaries.append(ModuleSummary(
                name="main",
                path=path_str,
                description="Go entry point",
                key_classes=[],
                key_functions=["main"],
            ))

        # cmd/ 目录下的文件
        if "cmd" in f.path.parts:
            summaries.append(ModuleSummary(
                name=f.path.stem,
                path=path_str,
                description="CLI command entry point",
                key_classes=[],
                key_functions=[],
            ))

    return summaries[:3]


def _get_module_name(path: Path) -> str:
    """从文件路径推断模块名"""
    stem = path.stem
    if stem == "__init__":
        # 使用父目录名
        parts = path.parent.parts
        return parts[-1] if parts else stem
    return stem
