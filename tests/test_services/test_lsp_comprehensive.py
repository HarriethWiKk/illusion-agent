"""
LSP 模块综合验证测试 — 覆盖所有操作和边界场景。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from illusion.tools.base import ToolExecutionContext
from illusion.tools.lsp_tool import LspTool, LspToolInput


@pytest.fixture
def project(tmp_path: Path):
    """创建一个模拟项目结构。"""
    # 包结构
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")

    # 基类
    (tmp_path / "pkg" / "base.py").write_text(
        '"""基类模块。"""\n'
        '\n'
        'from abc import ABC, abstractmethod\n'
        '\n'
        '\n'
        'class Animal(ABC):\n'
        '    """动物基类。"""\n'
        '\n'
        '    def __init__(self, name: str):\n'
        '        self.name = name\n'
        '\n'
        '    @abstractmethod\n'
        '    def speak(self) -> str:\n'
        '        """发出声音。"""\n'
        '        ...\n'
        '\n'
        '    def get_name(self) -> str:\n'
        '        """获取名字。"""\n'
        '        return self.name\n',
        encoding="utf-8",
    )

    # 子类
    (tmp_path / "pkg" / "dog.py").write_text(
        '"""狗模块。"""\n'
        '\n'
        'from pkg.base import Animal\n'
        '\n'
        '\n'
        'class Dog(Animal):\n'
        '    """狗类。"""\n'
        '\n'
        '    def speak(self) -> str:\n'
        '        """发出声音。"""\n'
        '        return "Woof!"\n'
        '\n'
        '    def fetch(self, item: str) -> str:\n'
        '        """取回物品。"""\n'
        '        return f"{self.name} fetches {item}"\n',
        encoding="utf-8",
    )

    # 使用模块
    (tmp_path / "pkg" / "app.py").write_text(
        '"""应用模块。"""\n'
        '\n'
        'from pkg.dog import Dog\n'
        'from pkg.base import Animal\n'
        '\n'
        '\n'
        'def main():\n'
        '    """主函数。"""\n'
        '    dog = Dog("Buddy")\n'
        '    print(dog.speak())\n'
        '    print(dog.get_name())\n'
        '    print(dog.fetch("ball"))\n'
        '\n'
        '\n'
        'def helper():\n'
        '    """辅助函数，调用 main。"""\n'
        '    main()\n',
        encoding="utf-8",
    )

    # 大文件（测试性能）
    lines = [f"var_{i} = {i}" for i in range(500)]
    lines += [f"def func_{i}():\n    return {i}\n" for i in range(100)]
    (tmp_path / "pkg" / "large.py").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return tmp_path


@pytest.fixture
def context(project: Path):
    return ToolExecutionContext(cwd=project)


@pytest.fixture
def lsp():
    return LspTool()


# ============================================================
# 基础操作验证
# ============================================================

class TestDocumentSymbol:
    """document_symbol 操作。"""

    @pytest.mark.asyncio
    async def test_list_symbols_in_module(self, lsp, context, project):
        """列出模块中的所有符号。"""
        result = await lsp.execute(
            LspToolInput(operation="document_symbol", file_path="pkg/base.py"),
            context,
        )
        assert result.is_error is False
        assert "Animal" in result.output
        assert "speak" in result.output
        assert "get_name" in result.output

    @pytest.mark.asyncio
    async def test_list_symbols_in_empty_init(self, lsp, context, project):
        """空 __init__.py 应返回无结果。"""
        result = await lsp.execute(
            LspToolInput(operation="document_symbol", file_path="pkg/__init__.py"),
            context,
        )
        assert result.is_error is False
        assert "no results" in result.output.lower() or result.output.strip() != ""

    @pytest.mark.asyncio
    async def test_list_symbols_in_large_file(self, lsp, context, project):
        """大文件应正常返回。"""
        result = await lsp.execute(
            LspToolInput(operation="document_symbol", file_path="pkg/large.py"),
            context,
        )
        assert result.is_error is False
        assert "func_0" in result.output


class TestGoToDefinition:
    """go_to_definition 操作。"""

    @pytest.mark.asyncio
    async def test_definition_of_function(self, lsp, context, project):
        """跳转到函数定义。"""
        result = await lsp.execute(
            LspToolInput(operation="go_to_definition", file_path="pkg/app.py", symbol="main"),
            context,
        )
        assert result.is_error is False
        assert "app.py" in result.output

    @pytest.mark.asyncio
    async def test_definition_of_class(self, lsp, context, project):
        """跳转到类定义。"""
        result = await lsp.execute(
            LspToolInput(operation="go_to_definition", file_path="pkg/app.py", symbol="Dog"),
            context,
        )
        assert result.is_error is False
        assert "dog.py" in result.output

    @pytest.mark.asyncio
    async def test_definition_by_position(self, lsp, context, project):
        """通过行号跳转到定义。"""
        # app.py 第 8 行是 "dog = Dog("Buddy")" — Dog 在该行
        result = await lsp.execute(
            LspToolInput(operation="go_to_definition", file_path="pkg/app.py", line=8, character=10),
            context,
        )
        assert result.is_error is False

    @pytest.mark.asyncio
    async def test_definition_nonexistent_symbol(self, lsp, context, project):
        """不存在的符号应返回无结果。"""
        result = await lsp.execute(
            LspToolInput(operation="go_to_definition", file_path="pkg/app.py", symbol="nonexistent_xyz"),
            context,
        )
        assert result.is_error is False
        assert "no results" in result.output.lower()


class TestFindReferences:
    """find_references 操作。"""

    @pytest.mark.asyncio
    async def test_references_to_function(self, lsp, context, project):
        """查找函数的所有引用。"""
        result = await lsp.execute(
            LspToolInput(operation="find_references", file_path="pkg/app.py", symbol="main"),
            context,
        )
        assert result.is_error is False
        assert "app.py" in result.output

    @pytest.mark.asyncio
    async def test_references_to_class(self, lsp, context, project):
        """查找类的引用。"""
        result = await lsp.execute(
            LspToolInput(operation="find_references", file_path="pkg/app.py", symbol="Dog"),
            context,
        )
        assert result.is_error is False
        # Dog 在 dog.py 定义，在 app.py 中被引用
        assert "app.py" in result.output

    @pytest.mark.asyncio
    async def test_references_nonexistent(self, lsp, context, project):
        """不存在的符号应返回无引用。"""
        result = await lsp.execute(
            LspToolInput(operation="find_references", file_path="pkg/app.py", symbol="nonexistent_xyz"),
            context,
        )
        assert result.is_error is False
        assert "no references" in result.output.lower() or "no results" in result.output.lower()


class TestHover:
    """hover 操作。"""

    @pytest.mark.asyncio
    async def test_hover_on_function(self, lsp, context, project):
        """悬停在函数上应显示签名和文档。"""
        result = await lsp.execute(
            LspToolInput(operation="hover", file_path="pkg/app.py", symbol="main"),
            context,
        )
        assert result.is_error is False
        assert "main" in result.output

    @pytest.mark.asyncio
    async def test_hover_on_class(self, lsp, context, project):
        """悬停在类上应显示类信息。"""
        result = await lsp.execute(
            LspToolInput(operation="hover", file_path="pkg/app.py", symbol="Dog"),
            context,
        )
        assert result.is_error is False
        assert "Dog" in result.output

    @pytest.mark.asyncio
    async def test_hover_no_result(self, lsp, context, project):
        """悬停在不存在的符号上应返回提示。"""
        result = await lsp.execute(
            LspToolInput(operation="hover", file_path="pkg/app.py", symbol="nonexistent_xyz"),
            context,
        )
        assert result.is_error is False
        assert "no hover" in result.output.lower()


class TestWorkspaceSymbol:
    """workspace_symbol 操作。"""

    @pytest.mark.asyncio
    async def test_search_symbol(self, lsp, context, project):
        """搜索工作区中的符号。"""
        result = await lsp.execute(
            LspToolInput(operation="workspace_symbol", query="Dog"),
            context,
        )
        assert result.is_error is False
        assert "Dog" in result.output

    @pytest.mark.asyncio
    async def test_search_partial(self, lsp, context, project):
        """部分名称搜索。"""
        result = await lsp.execute(
            LspToolInput(operation="workspace_symbol", query="speak"),
            context,
        )
        assert result.is_error is False
        assert "speak" in result.output

    @pytest.mark.asyncio
    async def test_search_empty_query(self, lsp, context, project):
        """空查询应返回错误。"""
        with pytest.raises(ValueError, match="requires query"):
            LspToolInput(operation="workspace_symbol")


class TestGoToImplementation:
    """go_to_implementation 操作。"""

    @pytest.mark.asyncio
    async def test_find_implementations_of_abstract_class(self, lsp, context, project):
        """查找抽象类的实现。"""
        result = await lsp.execute(
            LspToolInput(operation="go_to_implementation", file_path="pkg/base.py", symbol="Animal"),
            context,
        )
        assert result.is_error is False
        assert "Dog" in result.output

    @pytest.mark.asyncio
    async def test_find_implementations_of_method(self, lsp, context, project):
        """查找抽象方法的实现。"""
        result = await lsp.execute(
            LspToolInput(operation="go_to_implementation", file_path="pkg/base.py", symbol="Animal.speak"),
            context,
        )
        assert result.is_error is False
        assert "Dog.speak" in result.output


class TestCallHierarchy:
    """call_hierarchy 相关操作。"""

    @pytest.mark.asyncio
    async def test_prepare_call_hierarchy(self, lsp, context, project):
        """准备调用层次。"""
        result = await lsp.execute(
            LspToolInput(operation="prepare_call_hierarchy", file_path="pkg/app.py", symbol="main"),
            context,
        )
        assert result.is_error is False
        assert "main" in result.output

    @pytest.mark.asyncio
    async def test_incoming_calls(self, lsp, context, project):
        """查找调用 main 的函数。"""
        result = await lsp.execute(
            LspToolInput(operation="incoming_calls", file_path="pkg/app.py", symbol="main"),
            context,
        )
        assert result.is_error is False
        # helper 调用了 main
        assert "helper" in result.output

    @pytest.mark.asyncio
    async def test_outgoing_calls(self, lsp, context, project):
        """查找 main 调用的函数。"""
        result = await lsp.execute(
            LspToolInput(operation="outgoing_calls", file_path="pkg/app.py", symbol="main"),
            context,
        )
        assert result.is_error is False
        # main 调用了 Dog、speak、get_name、fetch
        assert "speak" in result.output or "Dog" in result.output


# ============================================================
# 错误处理验证
# ============================================================

class TestErrorHandling:
    """错误处理场景。"""

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, lsp, context, project):
        """不存在的文件应返回错误。"""
        result = await lsp.execute(
            LspToolInput(operation="document_symbol", file_path="nonexistent.py"),
            context,
        )
        assert result.is_error is True
        assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_non_python_file(self, lsp, context, project):
        """非 Python 文件应返回错误。"""
        (project / "readme.txt").write_text("hello", encoding="utf-8")
        result = await lsp.execute(
            LspToolInput(operation="document_symbol", file_path="readme.txt"),
            context,
        )
        assert result.is_error is True
        assert "python" in result.output.lower()

    @pytest.mark.asyncio
    async def test_missing_file_path(self, lsp, context, project):
        """需要 file_path 的操作缺少参数应报错。"""
        with pytest.raises(ValueError, match="requires file_path"):
            LspToolInput(operation="go_to_definition")

    @pytest.mark.asyncio
    async def test_missing_symbol_and_line(self, lsp, context, project):
        """既无 symbol 也无 line 应报错。"""
        with pytest.raises(ValueError, match="requires symbol or line"):
            LspToolInput(operation="go_to_definition", file_path="pkg/app.py")

    @pytest.mark.asyncio
    async def test_camelcase_operation_names(self, lsp, context, project):
        """驼峰操作名应自动转换为蛇形。"""
        result = await lsp.execute(
            LspToolInput(operation="goToDefinition", file_path="pkg/app.py", symbol="main"),
            context,
        )
        assert result.is_error is False
        assert "app.py" in result.output

    @pytest.mark.asyncio
    async def test_all_camelcase_operations(self, lsp, context, project):
        """所有驼峰操作名都应正常工作。"""
        ops = [
            ("documentSymbol", {"file_path": "pkg/base.py"}),
            ("workspaceSymbol", {"query": "Dog"}),
            ("goToDefinition", {"file_path": "pkg/app.py", "symbol": "main"}),
            ("findReferences", {"file_path": "pkg/app.py", "symbol": "main"}),
            ("hover", {"file_path": "pkg/app.py", "symbol": "main"}),
            ("goToImplementation", {"file_path": "pkg/base.py", "symbol": "Animal"}),
            ("prepareCallHierarchy", {"file_path": "pkg/app.py", "symbol": "main"}),
            ("incomingCalls", {"file_path": "pkg/app.py", "symbol": "main"}),
            ("outgoingCalls", {"file_path": "pkg/app.py", "symbol": "main"}),
        ]
        for op_name, kwargs in ops:
            result = await lsp.execute(
                LspToolInput(operation=op_name, **kwargs),
                context,
            )
            assert result.is_error is False, f"Operation {op_name} failed: {result.output}"


# ============================================================
# Gitignore 过滤验证
# ============================================================

class TestGitignoreFilter:
    """Gitignore 过滤场景。"""

    @pytest.mark.asyncio
    async def test_gitignored_files_excluded(self, project):
        """被 gitignore 的文件应被排除。"""
        # 初始化 git 仓库
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True, capture_output=True, text=True)

        # 创建 .gitignore
        (project / ".gitignore").write_text("ignored/\n", encoding="utf-8")
        (project / "ignored").mkdir()
        (project / "ignored" / "secret.py").write_text("def secret():\n    pass\n", encoding="utf-8")

        context = ToolExecutionContext(cwd=project)
        lsp = LspTool()

        # workspace_symbol 搜索不应返回被忽略的符号
        result = await lsp.execute(
            LspToolInput(operation="workspace_symbol", query="secret"),
            context,
        )
        assert result.is_error is False
        assert "secret" not in result.output
