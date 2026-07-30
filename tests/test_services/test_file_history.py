"""FileHistoryState 持久化单元测试。"""
from __future__ import annotations

import json
from pathlib import Path

from illusion.services.file_history import (
    FileBackup,
    FileHistoryState,
    FileSnapshot,
    _state_path,
    load,
    save,
)


def test_save_load_roundtrip(tmp_path: Path) -> None:
    """save 后 load 应返回相等的状态。"""
    cwd = str(tmp_path)
    state = FileHistoryState(session_id="abc123", cwd=cwd)
    # 直接构造 snapshot，不依赖 make_snapshot（Task 2 才改签名）
    snap = FileSnapshot(message_id="msg-1", turn_index=0)
    snap.tracked_backups[str(tmp_path / "file.py")] = FileBackup(
        backup_name="a1b2c3d4e5f67890", version=1
    )
    state.snapshots.append(snap)
    state._turn_counter = 1
    state.tracked_files.add(str(tmp_path / "file.py"))

    save(state)

    loaded = load(cwd, "abc123")
    assert loaded is not None
    assert loaded.session_id == "abc123"
    assert loaded.cwd == cwd
    assert loaded._turn_counter == 1
    assert loaded.tracked_files == state.tracked_files
    assert len(loaded.snapshots) == 1
    s0 = loaded.snapshots[0]
    assert s0.message_id == "msg-1"
    assert s0.turn_index == 0
    key = str(tmp_path / "file.py")
    assert key in s0.tracked_backups
    assert s0.tracked_backups[key].backup_name == "a1b2c3d4e5f67890"
    assert s0.tracked_backups[key].version == 1


def test_load_nonexistent_returns_none(tmp_path: Path) -> None:
    """文件不存在时 load 返回 None。"""
    assert load(str(tmp_path), "abc123") is None


def test_load_corrupt_json_returns_none(tmp_path: Path) -> None:
    """JSON 损坏时 load 返回 None。"""
    path = _state_path(str(tmp_path), "abc123")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")
    assert load(str(tmp_path), "abc123") is None


def test_load_old_format_without_checkpoint_id_returns_none(tmp_path: Path) -> None:
    """旧格式 snapshot 缺失 checkpoint_id 时整体返回 None。"""
    path = _state_path(str(tmp_path), "abc123")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "session_id": "abc123",
        "cwd": str(tmp_path),
        "turn_counter": 1,
        "tracked_files": [],
        "snapshots": [
            {
                "message_id": "msg-1",
                "turn_index": 0,
                # 故意省略 checkpoint_id
                "tracked_backups": {},
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load(str(tmp_path), "abc123") is None


def test_load_with_checkpoint_count_aligns(tmp_path: Path) -> None:
    """load 传入 checkpoint_count 时丢弃 checkpoint_id >= count 的 snapshot。"""
    path = _state_path(str(tmp_path), "abc123")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "session_id": "abc123",
        "cwd": str(tmp_path),
        "turn_counter": 4,
        "tracked_files": [],
        "snapshots": [
            {"message_id": "1", "turn_index": 0, "checkpoint_id": 0, "tracked_backups": {}},
            {"message_id": "2", "turn_index": 1, "checkpoint_id": 1, "tracked_backups": {}},
            {"message_id": "3", "turn_index": 2, "checkpoint_id": 2, "tracked_backups": {}},
            {"message_id": "4", "turn_index": 3, "checkpoint_id": 3, "tracked_backups": {}},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load(str(tmp_path), "abc123", checkpoint_count=2)
    assert loaded is not None
    assert len(loaded.snapshots) == 2
    assert loaded.snapshots[0].checkpoint_id == 0
    assert loaded.snapshots[1].checkpoint_id == 1
    assert loaded._turn_counter == 2

    reloaded = load(str(tmp_path), "abc123")
    assert reloaded is not None
    assert len(reloaded.snapshots) == 2
