"""
文件周期清理工具
================

提供统一的 TTL 文件清理函数，供 tasks 日志、记忆活动日志等
多个子系统复用，避免各模块重复实现清理循环。

函数说明：
    - cleanup_old_files: 删除目录下超过保留期限的文件
"""

from __future__ import annotations

import time
from pathlib import Path

DEFAULT_TTL_DAYS = 7  # 默认保留天数


def cleanup_old_files(
    directory: Path,
    pattern: str = "*",
    *,
    max_age_days: int = DEFAULT_TTL_DAYS,
) -> int:
    """删除目录下 mtime 超过 max_age_days 天的文件。

    静默处理异常：目录不可访问、单个文件被占用或删除失败时
    跳过并继续，不影响调用方。

    Args:
        directory: 目标目录
        pattern: 文件匹配模式（glob，如 "*.log" / "memory_*.log"）
        max_age_days: 保留天数，超过即删除

    Returns:
        int: 删除的文件数量
    """
    try:
        cutoff = time.time() - max_age_days * 24 * 3600
        removed = 0
        for path in directory.glob(pattern):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                # 单文件不可访问/被占用时跳过
                continue
        return removed
    except OSError:
        # 目录不可访问时静默跳过
        return 0
