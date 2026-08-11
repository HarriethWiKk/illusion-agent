"""文件周期清理工具测试。"""

from __future__ import annotations

import os
import time
from pathlib import Path

from illusion.utils.log_cleanup import cleanup_old_files


def _make_old_file(path: Path, *, age_days: float) -> None:
    """创建 mtime 为 age_days 天前的文件。"""
    path.write_text("old", encoding="utf-8")
    old = time.time() - age_days * 24 * 3600
    os.utime(path, (old, old))


def test_cleanup_removes_old_files(tmp_path: Path):
    old = tmp_path / "old.log"
    _make_old_file(old, age_days=10)

    removed = cleanup_old_files(tmp_path, "*.log", max_age_days=7)
    assert removed == 1
    assert not old.exists()


def test_cleanup_keeps_recent_files(tmp_path: Path):
    recent = tmp_path / "recent.log"
    recent.write_text("new", encoding="utf-8")  # mtime = now

    removed = cleanup_old_files(tmp_path, "*.log", max_age_days=7)
    assert removed == 0
    assert recent.exists()


def test_cleanup_respects_pattern(tmp_path: Path):
    old_memory = tmp_path / "memory_extract.log"
    _make_old_file(old_memory, age_days=10)
    old_other = tmp_path / "other.log"
    _make_old_file(old_other, age_days=10)

    removed = cleanup_old_files(tmp_path, "memory_*.log", max_age_days=7)
    assert removed == 1
    assert not old_memory.exists()
    assert old_other.exists()


def test_cleanup_missing_dir(tmp_path: Path):
    """目录不存在时静默返回 0。"""
    removed = cleanup_old_files(tmp_path / "nope", "*.log")
    assert removed == 0


def test_cleanup_custom_ttl(tmp_path: Path):
    file_5d = tmp_path / "five.log"
    _make_old_file(file_5d, age_days=5)

    # 3 天 TTL → 删除；10 天 TTL → 保留
    assert cleanup_old_files(tmp_path, "*.log", max_age_days=3) == 1
    file_5d_2 = tmp_path / "five2.log"
    _make_old_file(file_5d_2, age_days=5)
    assert cleanup_old_files(tmp_path, "*.log", max_age_days=10) == 0
