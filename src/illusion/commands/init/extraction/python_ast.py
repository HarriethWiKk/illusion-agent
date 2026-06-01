"""
Python AST 分析器
=================

使用 Python 标准库 ast 模块分析 .py 文件，提取类、函数、导入、常量等符号信息。
支持 docstring 风格检测（google/numpy/sphinx）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from illusion.commands.init.types import PythonModuleInfo, SymbolInfo

# 分析限制
_MAX_FILE_SIZE = 100_000  # 100KB
_MAX_FILES = 200  # 最多分析文件数


def analyze_python_file(path: Path) -> PythonModuleInfo | None:
    """分析单个 Python 文件的 AST

    Args:
        path: Python 文件路径（绝对路径）

    Returns:
        分析结果，解析失败返回 None
    """
    try:
        size = path.stat().st_size
        if size > _MAX_FILE_SIZE or size == 0:
            return None

        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))

        docstring = ast.get_docstring(tree)
        classes = _extract_classes(tree)
        functions = _extract_functions(tree)
        imports = _extract_imports(tree)
        constants = _extract_constants(tree)

        return PythonModuleInfo(
            path=path,
            docstring=docstring,
            classes=classes,
            functions=functions,
            imports=imports,
            constants=constants,
        )
    except (SyntaxError, OSError, ValueError):
        return None


def analyze_python_project(root: Path, py_files: list[Path]) -> list[PythonModuleInfo]:
    """分析项目中所有 Python 文件

    Args:
        root: 项目根目录
        py_files: Python 文件路径列表（绝对路径）

    Returns:
        分析结果列表（跳过解析失败的文件）
    """
    # 过滤和排序：排除 __pycache__，优先分析非测试文件
    filtered = []
    test_files = []
    for p in py_files:
        parts = p.parts
        if "__pycache__" in parts:
            continue
        if any(part.startswith("test_") or part.endswith("_test.py") for part in parts):
            test_files.append(p)
        else:
            filtered.append(p)

    # 非测试文件优先，总数限制
    ordered = filtered + test_files
    if len(ordered) > _MAX_FILES:
        ordered = ordered[:_MAX_FILES]

    results = []
    for path in ordered:
        info = analyze_python_file(path)
        if info is not None:
            results.append(info)

    return results


def _extract_classes(tree: ast.Module) -> list[SymbolInfo]:
    """从 AST 提取类定义"""
    classes = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(ast.unparse(base))

            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(item.name)

            decorators = _extract_decorator_names(node.decorator_list)
            docstring = ast.get_docstring(node)

            classes.append(SymbolInfo(
                name=node.name,
                kind="class",
                line=node.lineno,
                docstring=docstring,
                decorators=decorators,
                bases=bases,
                signature=f"({', '.join(methods[:5])}{'...' if len(methods) > 5 else ''})" if methods else None,
            ))
    return classes


def _extract_functions(tree: ast.Module) -> list[SymbolInfo]:
    """从 AST 提取顶层函数定义"""
    functions = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # 构建签名
            args = []
            for arg in node.args.args:
                if arg.arg != "self" and arg.arg != "cls":
                    arg_str = arg.arg
                    if arg.annotation:
                        arg_str += f": {ast.unparse(arg.annotation)}"
                    args.append(arg_str)

            ret_annotation = ""
            if node.returns:
                ret_annotation = f" -> {ast.unparse(node.returns)}"

            signature = f"({', '.join(args)}){ret_annotation}"
            decorators = _extract_decorator_names(node.decorator_list)
            docstring = ast.get_docstring(node)

            prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            functions.append(SymbolInfo(
                name=node.name,
                kind="function",
                line=node.lineno,
                docstring=docstring,
                decorators=decorators,
                signature=f"{prefix}{node.name}{signature}",
            ))
    return functions


def _extract_imports(tree: ast.Module) -> list[str]:
    """从 AST 提取导入语句"""
    imports = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _extract_constants(tree: ast.Module) -> list[tuple[str, str]]:
    """从 AST 提取顶层常量"""
    constants = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    value_str = ast.unparse(node.value)[:50]
                    constants.append((target.id, value_str))
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id.isupper():
                type_str = ast.unparse(node.annotation)[:50]
                constants.append((node.target.id, type_str))
    return constants


def _extract_decorator_names(decorators: list[ast.expr]) -> list[str]:
    """提取装饰器名称"""
    names = []
    for dec in decorators:
        if isinstance(dec, ast.Name):
            names.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            names.append(ast.unparse(dec))
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name):
                names.append(dec.func.id)
            elif isinstance(dec.func, ast.Attribute):
                names.append(ast.unparse(dec.func))
    return names


def detect_docstring_style_from_modules(modules: list[PythonModuleInfo]) -> str | None:
    """从多个模块的 docstring 检测文档风格

    采样前 20 个有 docstring 的模块，检查模式匹配。

    Args:
        modules: Python 模块分析结果列表

    Returns:
        "google", "numpy", "sphinx" 或 None
    """
    google_count = 0
    numpy_count = 0
    sphinx_count = 0
    sampled = 0

    for mod in modules:
        docstrings_to_check = []
        if mod.docstring:
            docstrings_to_check.append(mod.docstring)
        for cls in mod.classes:
            if cls.docstring:
                docstrings_to_check.append(cls.docstring)
        for func in mod.functions:
            if func.docstring:
                docstrings_to_check.append(func.docstring)

        for ds in docstrings_to_check:
            if sampled >= 20:
                break
            sampled += 1

            # Google style: Args:, Returns:, Raises:
            if re.search(r"^\s*(Args|Returns|Raises|Attributes|Example|Note):\s*$", ds, re.MULTILINE):
                google_count += 1
            # NumPy style: Parameters\n----------
            if re.search(r"(Parameters|Returns|Raises|Examples)\s*\n\s*-{3,}", ds):
                numpy_count += 1
            # Sphinx style: :param, :type, :returns:, :rtype:
            if re.search(r":(param|type|returns?|rtype|raises?)\s", ds):
                sphinx_count += 1

        if sampled >= 20:
            break

    if sampled < 2:
        return None

    threshold = sampled * 0.3
    if google_count >= threshold and google_count >= numpy_count and google_count >= sphinx_count:
        return "google"
    if numpy_count >= threshold and numpy_count >= sphinx_count:
        return "numpy"
    if sphinx_count >= threshold:
        return "sphinx"
    return None


def detect_type_hints_usage(modules: list[PythonModuleInfo]) -> bool:
    """检测项目是否广泛使用类型注解

    采样函数，如果有 50%+ 使用了类型注解则返回 True。
    """
    total = 0
    with_hints = 0

    for mod in modules:
        for func in mod.functions:
            total += 1
            sig = func.signature or ""
            if "->" in sig or ": " in sig:
                with_hints += 1
        if total >= 30:
            break

    if total < 5:
        return False
    return (with_hints / total) >= 0.5
