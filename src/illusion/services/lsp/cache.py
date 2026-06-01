"""
AST LRU 缓存与文件同步通知。

提供 AstCache 缓存已解析的 AST 树，FileChangeNotifier 在文件变更时清除缓存。
"""

from __future__ import annotations

import ast
from collections import OrderedDict
from pathlib import Path


class AstCache:
    """LRU 缓存已解析的 AST 树，避免重复解析同一文件。"""

    def __init__(self, maxsize: int = 128):
        self._cache: OrderedDict[Path, tuple[ast.AST, float]] = OrderedDict()
        self._maxsize = maxsize

    def get(self, path: Path) -> ast.AST | None:
        """获取缓存的 AST 树，mtime 不匹配则返回 None。"""
        if path not in self._cache:
            return None
        tree, cached_mtime = self._cache[path]
        current_mtime = path.stat().st_mtime
        if current_mtime != cached_mtime:
            del self._cache[path]
            return None
        self._cache.move_to_end(path)
        return tree

    def get_or_parse(self, path: Path) -> ast.AST:
        """获取缓存的 AST 或解析并缓存。"""
        tree = self.get(path)
        if tree is not None:
            return tree
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        self.put(path, tree)
        return tree

    def put(self, path: Path, tree: ast.AST) -> None:
        """缓存 AST 树。"""
        mtime = path.stat().st_mtime
        self._cache[path] = (tree, mtime)
        self._cache.move_to_end(path)
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def invalidate(self, path: Path) -> None:
        """文件变更时清除缓存。"""
        self._cache.pop(path, None)


class FileChangeNotifier:
    """文件变更通知器，用于同步 AST 缓存。"""

    def __init__(self, cache: AstCache):
        self._cache = cache

    def on_file_changed(self, path: Path) -> None:
        """文件编辑后调用，清除 AST 缓存。"""
        self._cache.invalidate(path)

    def on_file_saved(self, path: Path) -> None:
        """文件保存后调用，清除缓存以便下次访问时重新解析。"""
        self._cache.invalidate(path)
