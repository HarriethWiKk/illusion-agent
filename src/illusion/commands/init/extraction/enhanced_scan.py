"""
非 Python 语言增强扫描器
========================

使用正则表达式提取 JS/TS/Rust/Go 等语言的关键符号声明。
不依赖 tree-sitter，仅做浅层扫描（每文件前 50 行）。
"""

from __future__ import annotations

import re
from pathlib import Path

# 每个文件最多扫描的行数
_MAX_LINES = 50

# 每种语言最多收集的符号数
_MAX_SYMBOLS_PER_LANG = 30


def scan_non_python(
    root: Path,
    files_by_lang: dict[str, list[Path]],
) -> dict[str, list[str]]:
    """扫描非 Python 语言的关键符号

    Args:
        root: 项目根目录
        files_by_lang: 语言 -> 文件路径列表（绝对路径）

    Returns:
        语言 -> 符号描述列表
    """
    result: dict[str, list[str]] = {}

    scanners = {
        "JavaScript": _scan_js_ts,
        "TypeScript": _scan_js_ts,
        "React": _scan_js_ts,
        "Rust": _scan_rust,
        "Go": _scan_go,
        "Java": _scan_java,
        "C#": _scan_csharp,
        "C++": _scan_cpp,
        "C": _scan_c,
        "Ruby": _scan_ruby,
    }

    for lang, files in files_by_lang.items():
        scanner = scanners.get(lang)
        if scanner:
            symbols = scanner(files)
            if symbols:
                result[lang] = symbols

    return result


def _scan_files(files: list[Path], patterns: list[re.Pattern[str]], max_symbols: int = _MAX_SYMBOLS_PER_LANG) -> list[str]:
    """通用文件扫描：对每个文件的前 N 行应用正则模式"""
    symbols: list[str] = []
    seen: set[str] = set()

    for path in files:
        if len(symbols) >= max_symbols:
            break
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(content.split("\n")):
                if i >= _MAX_LINES:
                    break
                for pattern in patterns:
                    match = pattern.search(line)
                    if match:
                        name = match.group(1)
                        if name not in seen and len(name) > 1:
                            seen.add(name)
                            symbols.append(name)
                        if len(symbols) >= max_symbols:
                            break
        except OSError:
            continue

    return symbols


def _scan_js_ts(files: list[Path]) -> list[str]:
    """扫描 JS/TS 文件的关键导出"""
    patterns = [
        re.compile(r"export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)"),
        re.compile(r"export\s+(?:abstract\s+)?class\s+(\w+)"),
        re.compile(r"export\s+(?:const|let|var)\s+(\w+)"),
        re.compile(r"export\s+interface\s+(\w+)"),
        re.compile(r"export\s+type\s+(\w+)"),
        re.compile(r"export\s+enum\s+(\w+)"),
        re.compile(r"(?:export\s+default\s+)?function\s+(\w+)"),
        re.compile(r"(?:export\s+)?class\s+(\w+)"),
    ]
    return _scan_files(files, patterns)


def _scan_rust(files: list[Path]) -> list[str]:
    """扫描 Rust 文件的 pub 定义"""
    patterns = [
        re.compile(r"pub\s+(?:async\s+)?fn\s+(\w+)"),
        re.compile(r"pub\s+struct\s+(\w+)"),
        re.compile(r"pub\s+enum\s+(\w+)"),
        re.compile(r"pub\s+trait\s+(\w+)"),
        re.compile(r"pub\s+type\s+(\w+)"),
        re.compile(r"impl\s+(\w+)"),
        re.compile(r"mod\s+(\w+)"),
    ]
    return _scan_files(files, patterns)


def _scan_go(files: list[Path]) -> list[str]:
    """扫描 Go 文件的导出类型和函数"""
    patterns = [
        re.compile(r"func\s+(?:\(\w+\s+\*?\w+\)\s+)?([A-Z]\w+)"),
        re.compile(r"type\s+([A-Z]\w+)\s+struct"),
        re.compile(r"type\s+([A-Z]\w+)\s+interface"),
        re.compile(r"type\s+(\w+)\s+\w+"),
    ]
    return _scan_files(files, patterns)


def _scan_java(files: list[Path]) -> list[str]:
    """扫描 Java 文件的类和接口"""
    patterns = [
        re.compile(r"public\s+(?:abstract\s+)?class\s+(\w+)"),
        re.compile(r"public\s+interface\s+(\w+)"),
        re.compile(r"public\s+enum\s+(\w+)"),
        re.compile(r"public\s+(?:static\s+)?(?:\w+\s+)+(\w+)\s*\("),
    ]
    return _scan_files(files, patterns)


def _scan_csharp(files: list[Path]) -> list[str]:
    """扫描 C# 文件的类和接口"""
    patterns = [
        re.compile(r"public\s+(?:abstract\s+|static\s+)?class\s+(\w+)"),
        re.compile(r"public\s+interface\s+(\w+)"),
        re.compile(r"public\s+enum\s+(\w+)"),
        re.compile(r"public\s+struct\s+(\w+)"),
        re.compile(r"namespace\s+(\w+(?:\.\w+)*)"),
    ]
    return _scan_files(files, patterns)


def _scan_cpp(files: list[Path]) -> list[str]:
    """扫描 C++ 文件的类和函数"""
    patterns = [
        re.compile(r"class\s+(\w+)"),
        re.compile(r"struct\s+(\w+)"),
        re.compile(r"(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*(?:const\s*)?(?:override\s*)?\{"),
        re.compile(r"namespace\s+(\w+)"),
    ]
    return _scan_files(files, patterns)


def _scan_c(files: list[Path]) -> list[str]:
    """扫描 C 文件的函数声明"""
    patterns = [
        re.compile(r"^(?:\w+\s+)+(\w+)\s*\([^)]*\)\s*\{"),
        re.compile(r"struct\s+(\w+)"),
        re.compile(r"typedef\s+struct\s+(\w+)"),
    ]
    return _scan_files(files, patterns)


def _scan_ruby(files: list[Path]) -> list[str]:
    """扫描 Ruby 文件的类和模块"""
    patterns = [
        re.compile(r"class\s+(\w+)"),
        re.compile(r"module\s+(\w+)"),
        re.compile(r"def\s+(\w+)"),
    ]
    return _scan_files(files, patterns)
