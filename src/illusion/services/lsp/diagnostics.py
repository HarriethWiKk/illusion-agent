"""
诊断注册表 — 支持去重、限流和跨轮次缓存。
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Diagnostic:
    """诊断信息。"""

    message: str
    severity: str  # "error" | "warning" | "info" | "hint"
    file_path: Path
    line: int
    character: int
    source: str = ""


class DiagnosticRegistry:
    """诊断信息注册表，支持去重、限流和跨轮次缓存。"""

    MAX_PER_FILE = 10
    MAX_TOTAL = 30
    MAX_CACHED_FILES = 500

    def __init__(self) -> None:
        self._delivered: OrderedDict[str, set[str]] = OrderedDict()

    def register(self, file_path: Path, diagnostics: list[Diagnostic]) -> list[Diagnostic]:
        """注册新诊断，返回未投递过的诊断列表。"""
        # 批次内去重
        seen: set[str] = set()
        unique: list[Diagnostic] = []
        for d in diagnostics:
            h = self._hash_diagnostic(d)
            if h not in seen:
                seen.add(h)
                unique.append(d)

        # 跨轮次去重
        key = str(file_path)
        delivered = self._delivered.get(key, set())
        new_diags: list[Diagnostic] = []
        for d in unique:
            h = self._hash_diagnostic(d)
            if h not in delivered:
                delivered.add(h)
                new_diags.append(d)

        self._delivered[key] = delivered
        self._evict_if_needed()

        # 按严重性排序后限流
        severity_order = {"error": 0, "warning": 1, "info": 2, "hint": 3}
        new_diags.sort(key=lambda d: severity_order.get(d.severity, 4))
        return new_diags[: self.MAX_PER_FILE]

    def clear_file(self, file_path: Path) -> None:
        """文件编辑时清除已投递缓存。"""
        self._delivered.pop(str(file_path), None)

    def _hash_diagnostic(self, d: Diagnostic) -> str:
        return f"{d.message}:{d.severity}:{d.line}:{d.character}:{d.source}"

    def _evict_if_needed(self) -> None:
        while len(self._delivered) > self.MAX_CACHED_FILES:
            self._delivered.popitem(last=False)

    def format_diagnostics(self, diagnostics: list[Diagnostic], root: Path) -> str:
        """格式化诊断信息为可读文本。"""
        if not diagnostics:
            return "(no diagnostics)"
        lines = [f"Found {len(diagnostics)} diagnostics:"]
        for d in diagnostics[: self.MAX_TOTAL]:
            try:
                rel = str(d.file_path.relative_to(root))
            except ValueError:
                rel = str(d.file_path)
            lines.append(f"  [{d.severity.upper()}] {rel}:{d.line}:{d.character} - {d.message}")
        return "\n".join(lines)
