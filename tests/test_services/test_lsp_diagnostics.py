"""
诊断注册表测试 — 去重、限流、跨轮次缓存。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from illusion.services.lsp.diagnostics import Diagnostic, DiagnosticRegistry


class TestDiagnosticRegistry:
    """DiagnosticRegistry 测试。"""

    def _make_diag(self, message: str = "error", severity: str = "error", line: int = 1) -> Diagnostic:
        return Diagnostic(
            message=message,
            severity=severity,
            file_path=Path("test.py"),
            line=line,
            character=1,
            source="test",
        )

    def test_register_returns_new_diagnostics(self):
        """首次注册的诊断应全部返回。"""
        registry = DiagnosticRegistry()
        diags = [self._make_diag("error 1"), self._make_diag("error 2")]
        result = registry.register(Path("test.py"), diags)
        assert len(result) == 2

    def test_dedup_within_batch(self):
        """同一批次中重复的诊断应被去重。"""
        registry = DiagnosticRegistry()
        diags = [self._make_diag("same error"), self._make_diag("same error")]
        result = registry.register(Path("test.py"), diags)
        assert len(result) == 1

    def test_dedup_across_rounds(self):
        """跨轮次的重复诊断不应再次返回。"""
        registry = DiagnosticRegistry()
        diags = [self._make_diag("persistent error")]

        result1 = registry.register(Path("test.py"), diags)
        assert len(result1) == 1

        result2 = registry.register(Path("test.py"), diags)
        assert len(result2) == 0

    def test_clear_file_resets_cache(self):
        """清除文件缓存后，已投递的诊断可再次返回。"""
        registry = DiagnosticRegistry()
        diags = [self._make_diag("error")]

        registry.register(Path("test.py"), diags)
        registry.clear_file(Path("test.py"))

        result = registry.register(Path("test.py"), diags)
        assert len(result) == 1

    def test_throttle_per_file(self):
        """每文件最多返回 MAX_PER_FILE 条诊断。"""
        registry = DiagnosticRegistry()
        diags = [self._make_diag(f"error {i}", line=i) for i in range(20)]
        result = registry.register(Path("test.py"), diags)
        assert len(result) == DiagnosticRegistry.MAX_PER_FILE

    def test_severity_sorting(self):
        """诊断应按严重性排序（error > warning > info > hint）。"""
        registry = DiagnosticRegistry()
        diags = [
            self._make_diag("info", severity="info"),
            self._make_diag("error", severity="error"),
            self._make_diag("warning", severity="warning"),
        ]
        result = registry.register(Path("test.py"), diags)
        assert result[0].severity == "error"
        assert result[1].severity == "warning"
        assert result[2].severity == "info"

    def test_format_diagnostics(self):
        """格式化诊断信息为可读文本。"""
        registry = DiagnosticRegistry()
        diags = [self._make_diag("undefined name", severity="error", line=10)]
        text = registry.format_diagnostics(diags, Path("/project"))
        assert "Found 1 diagnostics:" in text
        assert "[ERROR]" in text
        assert "undefined name" in text

    def test_format_empty_diagnostics(self):
        """空诊断列表应返回提示文本。"""
        registry = DiagnosticRegistry()
        text = registry.format_diagnostics([], Path("/project"))
        assert "(no diagnostics)" in text

    def test_eviction_of_old_entries(self):
        """超出 MAX_CACHED_FILES 时应淘汰最旧的条目。"""
        registry = DiagnosticRegistry()
        for i in range(DiagnosticRegistry.MAX_CACHED_FILES + 10):
            registry.register(Path(f"file_{i}.py"), [self._make_diag(f"error {i}")])

        assert len(registry._delivered) <= DiagnosticRegistry.MAX_CACHED_FILES

        result = registry.register(Path("file_0.py"), [self._make_diag("error 0")])
        assert len(result) == 1
