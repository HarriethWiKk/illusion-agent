"""Tests for session persistence."""

from __future__ import annotations

from pathlib import Path

from illusion.engine.messages import ConversationMessage, TextBlock
from illusion.services.session_storage import (
    export_session_markdown,
    read_meta,
    write_meta,
)


def test_write_and_read_meta(tmp_path: Path, monkeypatch):
    """write_meta / read_meta 验证新的会话元数据读写（替代旧 save/load_session_snapshot）。"""
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()

    meta = {
        "session_id": "abc",
        "cwd": str(project),
        "model": "claude-test",
        "summary": "",
        "message_count": 1,
    }
    write_meta(cwd=project, session_id="abc", meta=meta)

    loaded = read_meta(project, "abc")
    assert loaded is not None
    assert loaded["model"] == "claude-test"
    assert loaded["session_id"] == "abc"


def test_export_session_markdown(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()

    path = export_session_markdown(
        cwd=project,
        messages=[
            ConversationMessage(role="user", content=[TextBlock(text="hello")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="world")]),
        ],
    )

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "IllusionAgent Session Transcript" in content
    assert "hello" in content
    assert "world" in content


def test_count_turns() -> None:
    """测试轮次计数函数"""
    from illusion.services.session_storage import count_turns

    # 空消息列表
    assert count_turns([]) == 0

    # 只有系统消息
    messages = [
        {"role": "system", "text": "System prompt"},
    ]
    assert count_turns(messages) == 0

    # 只有用户消息
    messages = [
        {"role": "user", "text": "Hello"},
    ]
    assert count_turns(messages) == 1

    # 用户消息和助手消息
    messages = [
        {"role": "user", "text": "Hello"},
        {"role": "assistant", "text": "Hi there"},
        {"role": "user", "text": "How are you?"},
        {"role": "assistant", "text": "I'm good"},
    ]
    assert count_turns(messages) == 2

    # 包含斜杠命令
    messages = [
        {"role": "user", "text": "/help"},
        {"role": "assistant", "text": "Here are the commands..."},
        {"role": "user", "text": "Hello"},
        {"role": "assistant", "text": "Hi there"},
    ]
    assert count_turns(messages) == 1

    # 包含空消息
    messages = [
        {"role": "user", "text": ""},
        {"role": "user", "text": "Hello"},
    ]
    assert count_turns(messages) == 1

    # 包含 content 数组格式
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "Hello"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Hi"}]},
    ]
    assert count_turns(messages) == 1


def test_save_load_delete_pending_plan_approval(tmp_path, monkeypatch):
    """测试 pending plan approval 的保存、加载、删除"""
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    from illusion.services.session_storage import (
        delete_pending_plan_approval,
        load_pending_plan_approval,
        save_pending_plan_approval,
    )

    plan = "# My Plan\n\nStep 1: Do X\nStep 2: Do Y"
    plan_path = "/home/user/.illusion/plans/my-plan.md"

    save_pending_plan_approval(
        cwd=tmp_path,
        session_id="abc123",
        plan=plan,
        plan_path=plan_path,
    )

    loaded = load_pending_plan_approval(tmp_path, "abc123")
    assert loaded is not None
    assert loaded["plan"] == plan
    assert loaded["plan_path"] == plan_path
    assert loaded["session_id"] == "abc123"

    deleted = delete_pending_plan_approval(tmp_path, "abc123")
    assert deleted is True

    loaded_after = load_pending_plan_approval(tmp_path, "abc123")
    assert loaded_after is None


def test_save_load_delete_pending_permission(tmp_path, monkeypatch):
    """测试 pending-permission 持久化函数"""
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    from illusion.services.session_storage import (
        delete_pending_permission,
        load_pending_permission,
        save_pending_permission,
    )
    cwd = str(tmp_path / "project")
    session_id = "test-session-001"

    # 保存
    path = save_pending_permission(
        cwd=cwd,
        session_id=session_id,
        tool_name="write_file",
        reason="Mutating tools require user confirmation",
    )
    assert path.exists()

    # 加载
    data = load_pending_permission(cwd, session_id)
    assert data is not None
    assert data["tool_name"] == "write_file"
    assert data["reason"] == "Mutating tools require user confirmation"
    assert data["approved"] is False
    assert data["session_id"] == session_id

    # 删除
    delete_pending_permission(cwd, session_id)
    assert load_pending_permission(cwd, session_id) is None
