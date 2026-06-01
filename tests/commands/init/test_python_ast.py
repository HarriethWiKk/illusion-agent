"""Python AST 分析器测试"""

from pathlib import Path

from illusion.commands.init.extraction.python_ast import (
    analyze_python_file,
    analyze_python_project,
    detect_docstring_style_from_modules,
    detect_type_hints_usage,
)
from illusion.commands.init.types import PythonModuleInfo


def test_analyze_simple_file(tmp_path: Path):
    """测试分析简单 Python 文件"""
    source = '''"""Module docstring."""

import os
from pathlib import Path

class MyClass:
    """A class."""
    def method(self, x: int) -> str:
        """A method."""
        return str(x)

def helper(name: str) -> bool:
    """A helper function."""
    return bool(name)

MAX_RETRIES = 3
'''
    path = tmp_path / "test_mod.py"
    path.write_text(source)

    result = analyze_python_file(path)
    assert result is not None
    assert result.docstring == "Module docstring."
    assert len(result.classes) == 1
    assert result.classes[0].name == "MyClass"
    assert result.classes[0].docstring == "A class."
    assert len(result.functions) == 1
    assert result.functions[0].name == "helper"
    assert result.functions[0].docstring == "A helper function."
    assert "os" in result.imports
    assert "pathlib" in result.imports
    assert len(result.constants) >= 1
    assert result.constants[0][0] == "MAX_RETRIES"


def test_analyze_syntax_error(tmp_path: Path):
    """测试语法错误文件返回 None"""
    path = tmp_path / "bad.py"
    path.write_text("def broken(\n")

    result = analyze_python_file(path)
    assert result is None


def test_analyze_empty_file(tmp_path: Path):
    """测试空文件（0字节跳过）"""
    path = tmp_path / "empty.py"
    path.write_text("")

    result = analyze_python_file(path)
    assert result is None  # 0字节文件被跳过


def test_analyze_minimal_file(tmp_path: Path):
    """测试最小文件（只有注释）"""
    path = tmp_path / "minimal.py"
    path.write_text("# just a comment\n")

    result = analyze_python_file(path)
    assert result is not None
    assert result.docstring is None
    assert result.classes == []
    assert result.functions == []


def test_detect_google_docstring():
    """测试检测 Google 风格 docstring"""
    modules = [
        PythonModuleInfo(
            path=Path("test.py"),
            docstring=None,
            classes=[],
            functions=[
                _make_func_with_doc(
                    "foo",
                    "Do something.\n\nArgs:\n    x: input\n\nReturns:\n    result"
                ),
                _make_func_with_doc(
                    "bar",
                    "Do something else.\n\nArgs:\n    y: input\n\nReturns:\n    result"
                ),
                _make_func_with_doc(
                    "baz",
                    "Another.\n\nArgs:\n    z: input\n\nRaises:\n    ValueError"
                ),
            ],
            imports=[],
            constants=[],
        ),
    ]
    assert detect_docstring_style_from_modules(modules) == "google"


def test_detect_numpy_docstring():
    """测试检测 NumPy 风格 docstring"""
    modules = [
        PythonModuleInfo(
            path=Path("test.py"),
            docstring=None,
            classes=[],
            functions=[
                _make_func_with_doc(
                    "foo",
                    "Do something.\n\nParameters\n----------\nx : int\n    input\n\nReturns\n-------\nresult"
                ),
                _make_func_with_doc(
                    "bar",
                    "Another.\n\nParameters\n----------\ny : str\n    input\n\nReturns\n-------\nresult"
                ),
                _make_func_with_doc(
                    "baz",
                    "Third.\n\nParameters\n----------\nz : float\n    input"
                ),
            ],
            imports=[],
            constants=[],
        ),
    ]
    assert detect_docstring_style_from_modules(modules) == "numpy"


def test_detect_type_hints_true():
    """测试检测类型注解使用"""
    modules = [
        PythonModuleInfo(
            path=Path("test.py"),
            docstring=None,
            classes=[],
            functions=[
                _make_func_with_sig(f"func{i}", f"func{i}(x: int) -> str")
                for i in range(6)
            ],
            imports=[],
            constants=[],
        ),
    ]
    assert detect_type_hints_usage(modules) is True


def test_detect_type_hints_false():
    """测试检测无类型注解"""
    modules = [
        PythonModuleInfo(
            path=Path("test.py"),
            docstring=None,
            classes=[],
            functions=[
                _make_func_with_sig(f"func{i}", f"func{i}(x)")
                for i in range(6)
            ],
            imports=[],
            constants=[],
        ),
    ]
    assert detect_type_hints_usage(modules) is False


def test_analyze_python_project(tmp_path: Path):
    """测试批量分析 Python 文件"""
    (tmp_path / "mod1.py").write_text("def f(): pass\n")
    (tmp_path / "mod2.py").write_text("class C: pass\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "cached.py").write_text("# cached\n")

    py_files = list(tmp_path.glob("*.py"))
    results = analyze_python_project(tmp_path, py_files)
    assert len(results) >= 2


def _make_func_with_doc(name: str, docstring: str) -> __import__("illusion.commands.init.types", fromlist=["SymbolInfo"]).SymbolInfo:
    from illusion.commands.init.types import SymbolInfo
    return SymbolInfo(name=name, kind="function", line=1, docstring=docstring)


def _make_func_with_sig(name: str, signature: str) -> __import__("illusion.commands.init.types", fromlist=["SymbolInfo"]).SymbolInfo:
    from illusion.commands.init.types import SymbolInfo
    return SymbolInfo(name=name, kind="function", line=1, signature=signature)
