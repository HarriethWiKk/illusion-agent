"""Shared test fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """全局隔离数据与配置目录，防止测试污染真实 ~/.illusion/ 目录。

    同时隔离 ILLUSION_DATA_DIR（数据目录）和 ILLUSION_CONFIG_DIR（配置目录，
    memory 目录迁至此处），所有测试自动应用此 fixture，无需手动设置。
    """
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ILLUSION_CONFIG_DIR", str(tmp_path / "config"))
