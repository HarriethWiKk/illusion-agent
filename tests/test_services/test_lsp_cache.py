"""
AST LRU 缓存与文件同步通知测试。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from illusion.services.lsp.cache import AstCache, FileChangeNotifier


class TestAstCache:
    """AstCache 测试。"""

    def test_get_or_parse_returns_ast(self, tmp_path: Path):
        """解析并缓存 AST 树。"""
        source = tmp_path / "test.py"
        source.write_text("def hello():\n    return 1\n", encoding="utf-8")

        cache = AstCache()
        tree = cache.get_or_parse(source)
        assert tree is not None
        import ast
        assert isinstance(tree, ast.Module)

    def test_cache_hit(self, tmp_path: Path):
        """第二次访问同一文件应命中缓存。"""
        source = tmp_path / "test.py"
        source.write_text("x = 1\n", encoding="utf-8")

        cache = AstCache()
        tree1 = cache.get_or_parse(source)
        tree2 = cache.get_or_parse(source)
        assert tree1 is tree2

    def test_cache_miss_after_modification(self, tmp_path: Path):
        """文件修改后缓存应失效。"""
        source = tmp_path / "test.py"
        source.write_text("x = 1\n", encoding="utf-8")

        cache = AstCache()
        tree1 = cache.get_or_parse(source)

        time.sleep(0.05)
        source.write_text("x = 2\n", encoding="utf-8")

        tree2 = cache.get_or_parse(source)
        assert tree1 is not tree2

    def test_invalidate(self, tmp_path: Path):
        """手动使缓存失效。"""
        source = tmp_path / "test.py"
        source.write_text("x = 1\n", encoding="utf-8")

        cache = AstCache()
        tree1 = cache.get_or_parse(source)
        cache.invalidate(source)

        tree2 = cache.get_or_parse(source)
        assert tree1 is not tree2

    def test_lru_eviction(self, tmp_path: Path):
        """超出容量时淘汰最久未使用的条目。"""
        cache = AstCache(maxsize=2)

        files = []
        for i in range(3):
            f = tmp_path / f"test{i}.py"
            f.write_text(f"x = {i}\n", encoding="utf-8")
            files.append(f)

        cache.get_or_parse(files[0])
        cache.get_or_parse(files[1])
        cache.get_or_parse(files[2])  # 应淘汰 files[0]

        assert cache.get(files[0]) is None
        assert cache.get(files[1]) is not None
        assert cache.get(files[2]) is not None

    def test_get_returns_none_for_uncached(self, tmp_path: Path):
        """未缓存的文件返回 None。"""
        source = tmp_path / "test.py"
        source.write_text("x = 1\n", encoding="utf-8")

        cache = AstCache()
        assert cache.get(source) is None


class TestFileChangeNotifier:
    """FileChangeNotifier 测试。"""

    def test_on_file_changed_invalidates_cache(self, tmp_path: Path):
        """文件变更通知应清除缓存。"""
        source = tmp_path / "test.py"
        source.write_text("x = 1\n", encoding="utf-8")

        cache = AstCache()
        cache.get_or_parse(source)

        notifier = FileChangeNotifier(cache)
        notifier.on_file_changed(source)

        assert cache.get(source) is None

    def test_on_file_saved_invalidates_cache(self, tmp_path: Path):
        """文件保存通知应清除缓存。"""
        source = tmp_path / "test.py"
        source.write_text("x = 1\n", encoding="utf-8")

        cache = AstCache()
        cache.get_or_parse(source)

        notifier = FileChangeNotifier(cache)
        notifier.on_file_saved(source)

        assert cache.get(source) is None
