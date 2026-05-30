"""文件历史快照模块
================

本模块提供基于文件复制的快照管理，用于支持 /rewind 指令的文件回退。

参考 Claude Code 的 copy-on-write 方案：在工具修改文件前备份其内容，
rewind 时从备份恢复。不依赖 git，可跟踪任意路径的文件。

存储位置：~/.illusion/data/file-history/{session_id}/{sha256(path)[:16]}@v{N}

主要函数：
    - track_edit: 在工具修改文件前备份（copy-on-write）
    - make_snapshot: 创建快照边界（每条用户消息一次）
    - rewind_to: 回退到指定快照，恢复文件

使用示例：
    >>> from illusion.services.file_history import FileHistoryState
    >>> state = FileHistoryState(session_id="abc123", cwd="/project")
    >>> track_edit(state, "/project/file.py")
    >>> make_snapshot(state, "msg-uuid-1")
    >>> rewind_to(state, "msg-uuid-1")
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

from illusion.config.paths import get_config_dir


@dataclass
class FileBackup:
    """单个文件的备份记录。"""
    backup_name: str | None  # 备份文件名，None 表示文件当时不存在
    version: int


@dataclass
class FileSnapshot:
    """一个快照：关联到一条用户消息，包含所有跟踪文件的备份映射。"""
    message_id: str
    turn_index: int = 0  # 轮次索引（0-based）
    tracked_backups: dict[str, FileBackup] = field(default_factory=dict)


@dataclass
class FileHistoryState:
    """文件历史状态。"""
    session_id: str
    cwd: str
    snapshots: list[FileSnapshot] = field(default_factory=list)
    tracked_files: set[str] = field(default_factory=set)
    _turn_counter: int = 0  # 内部轮次计数器


def _backup_dir(session_id: str) -> Path:
    """返回备份存储目录。"""
    return get_config_dir() / "file-history" / session_id


def _backup_name(file_path: str, version: int = 1) -> str:
    """生成备份文件名：sha256(路径@vN)[:16]。不同版本生成不同文件名。"""
    return sha256(f"{file_path}@v{version}".encode("utf-8")).hexdigest()[:16]


def _backup_path(session_id: str, backup_name: str) -> Path:
    """返回备份文件的完整路径。"""
    return _backup_dir(session_id) / backup_name


def _resolve_path(file_path: str, cwd: str) -> str:
    """将路径转为绝对路径。"""
    p = Path(file_path)
    if p.is_absolute():
        return str(p)
    return str(Path(cwd) / file_path)


def track_edit(state: FileHistoryState, file_path: str) -> None:
    """在工具修改文件前备份（copy-on-write）。

    如果文件在当前快照中已被跟踪，跳过。否则：
    - 文件存在：复制到备份目录
    - 文件不存在：记录 None（标记为"文件当时不存在"）

    Args:
        state: 文件历史状态
        file_path: 即将被修改的文件路径
    """
    abs_path = _resolve_path(file_path, state.cwd)
    tracking_key = abs_path  # 使用绝对路径作为 key

    # 检查是否已在当前快照中跟踪
    if state.snapshots:
        current = state.snapshots[-1]
        if tracking_key in current.tracked_backups:
            return  # 已跟踪，跳过

    # 确定版本号：查找最近快照中此文件的备份版本
    version = 1
    for snap in reversed(state.snapshots):
        if tracking_key in snap.tracked_backups:
            version = snap.tracked_backups[tracking_key].version + 1
            break

    # 创建备份
    bname = _backup_name(abs_path, version)
    bpath = _backup_path(state.session_id, bname)

    if Path(abs_path).exists():
        # 文件存在：复制备份
        bpath.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(abs_path, bpath)
        backup = FileBackup(backup_name=bname, version=version)
    else:
        # 文件不存在（新文件）
        backup = FileBackup(backup_name=None, version=version)

    # 记录到当前快照
    if state.snapshots:
        state.snapshots[-1].tracked_backups[tracking_key] = backup

    state.tracked_files.add(tracking_key)


def make_snapshot(state: FileHistoryState, message_id: str) -> None:
    """创建快照边界。

    在用户发送消息时调用，为后续的工具编辑创建新的跟踪空间。

    Args:
        state: 文件历史状态
        message_id: 关联的消息 ID
    """
    snapshot = FileSnapshot(message_id=message_id, turn_index=state._turn_counter)
    state._turn_counter += 1
    state.snapshots.append(snapshot)
    # 最多保留 50 个快照
    if len(state.snapshots) > 50:
        evicted = state.snapshots[:-50]
        state.snapshots = state.snapshots[-50:]
        # 清理被驱逐快照的备份文件
        _cleanup_evicted(state, evicted)


def rewind_to(state: FileHistoryState, turn_index: int) -> list[str]:
    """撤销指定轮次的所有文件修改，并移除该轮及之后的快照。

    快照的备份记录的是工具执行前的文件状态，所以用目标快照自身的备份
    来恢复文件，就能撤销该轮工具对文件的修改。

    Args:
        state: 文件历史状态
        turn_index: 要撤销的轮次索引（0-based）

    Returns:
        list[str]: 被恢复的文件路径列表
    """
    # 找到目标快照（turn_index 匹配的最后一个）
    target = None
    target_idx = -1
    for i, snap in enumerate(state.snapshots):
        if snap.turn_index == turn_index:
            target = snap
            target_idx = i
    if target is None:
        return []

    changed: list[str] = []
    for tracking_key in state.tracked_files:
        backup = target.tracked_backups.get(tracking_key)
        if backup is None:
            # 目标快照没有此文件的备份，找最早的备份
            backup = _find_first_backup(state, tracking_key)
            if backup is None:
                continue

        if backup.backup_name is None:
            # 文件当时不存在：删除
            p = Path(tracking_key)
            if p.exists():
                p.unlink()
                changed.append(tracking_key)
        else:
            # 从备份恢复（备份内容 = 工具执行前的状态）
            bpath = _backup_path(state.session_id, backup.backup_name)
            if bpath.exists():
                p = Path(tracking_key)
                current_content = p.read_bytes() if p.exists() else None
                backup_content = bpath.read_bytes()
                if current_content != backup_content:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(bpath, tracking_key)
                    changed.append(tracking_key)

    # 移除目标快照及之后的所有快照
    evicted = state.snapshots[target_idx:]
    state.snapshots = state.snapshots[:target_idx]
    _cleanup_evicted(state, evicted)

    return changed


def _find_first_backup(state: FileHistoryState, tracking_key: str) -> FileBackup | None:
    """找到文件的最早备份。"""
    for snap in state.snapshots:
        backup = snap.tracked_backups.get(tracking_key)
        if backup is not None:
            return backup
    return None


def cleanup_file_history(session_id: str) -> None:
    """删除指定会话的文件历史目录。"""
    d = _backup_dir(session_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def cleanup_all_file_histories() -> int:
    """删除所有文件历史目录，返回删除的目录数。"""
    base = get_config_dir() / "file-history"
    if not base.exists():
        return 0
    count = 0
    for child in base.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
            count += 1
    # 如果 base 为空，删除它
    try:
        base.rmdir()
    except OSError:
        pass
    return count


def _cleanup_evicted(state: FileHistoryState, evicted: list[FileSnapshot]) -> None:
    """清理被驱逐快照的孤立备份文件。"""
    # 收集仍被引用的备份名
    still_referenced: set[str] = set()
    for snap in state.snapshots:
        for backup in snap.tracked_backups.values():
            if backup.backup_name:
                still_referenced.add(backup.backup_name)

    # 删除不再被引用的备份
    for snap in evicted:
        for backup in snap.tracked_backups.values():
            if backup.backup_name and backup.backup_name not in still_referenced:
                bpath = _backup_path(state.session_id, backup.backup_name)
                try:
                    bpath.unlink(missing_ok=True)
                except OSError:
                    pass
