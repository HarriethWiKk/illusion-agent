"""Tests for session persistence."""

from __future__ import annotations

from pathlib import Path

from illusion.api.usage import UsageSnapshot
from illusion.engine.messages import ConversationMessage, TextBlock
from illusion.services.session_storage import (
    export_session_markdown,
    load_session_snapshot,
    save_session_snapshot,
)


def test_save_and_load_session_snapshot(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()

    path = save_session_snapshot(
        cwd=project,
        model="claude-test",
        system_prompt="system",
        messages=[ConversationMessage(role="user", content=[TextBlock(text="hello")])],
        usage=UsageSnapshot(input_tokens=1, output_tokens=2),
    )

    assert path.exists()
    snapshot = load_session_snapshot(project)
    assert snapshot is not None
    assert snapshot["model"] == "claude-test"
    assert snapshot["usage"]["output_tokens"] == 2


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
    assert "IllusionCode Session Transcript" in content
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
    from illusion.services.session_storage import (
        save_pending_plan_approval,
        load_pending_plan_approval,
        delete_pending_plan_approval,
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
