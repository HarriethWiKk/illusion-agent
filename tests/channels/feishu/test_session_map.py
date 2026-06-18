"""飞书会话存储测试。"""
from __future__ import annotations

from pathlib import Path

from illusion.channels.base import InboundMessage
from illusion.channels.feishu.session_map import FeishuSession, FeishuSessionStore


def _msg(chat_id: str, user_id: str, chat_type: str = "dm") -> InboundMessage:
    """构造测试用入站消息。"""
    return InboundMessage(
        text="hi", chat_id=chat_id, chat_type=chat_type,
        user_id=user_id, user_name="tester", message_id="om_1",
    )


def test_build_session_key_dm(tmp_path: Path):
    """私聊按用户隔离。"""
    store = FeishuSessionStore(data_dir=tmp_path)
    assert store.build_session_key(_msg("ou_a", "ou_a", "dm")) == "u:ou_a"


def test_build_session_key_group_per_user(tmp_path: Path):
    """群组默认每用户隔离。"""
    store = FeishuSessionStore(data_dir=tmp_path, group_sessions_per_user=True)
    key = store.build_session_key(_msg("oc_room", "ou_a", "group"))
    assert key == "g:oc_room:ou_a"


def test_build_session_key_group_shared(tmp_path: Path):
    """群组可配置为共享会话。"""
    store = FeishuSessionStore(data_dir=tmp_path, group_sessions_per_user=False)
    key = store.build_session_key(_msg("oc_room", "ou_a", "group"))
    assert key == "g:oc_room"


def test_get_or_create_new_session(tmp_path: Path):
    """新 key 创建空会话。"""
    store = FeishuSessionStore(data_dir=tmp_path)
    session = store.get_or_create("u:ou_a", "ou_a", "dm")
    assert isinstance(session, FeishuSession)
    assert session.messages == []
    assert session.session_id  # 非空 ID


def test_get_or_create_returns_existing(tmp_path: Path):
    """重复 get 返回同一会话。"""
    store = FeishuSessionStore(data_dir=tmp_path)
    s1 = store.get_or_create("u:ou_a", "ou_a", "dm")
    store.save(s1, [{"role": "user", "content": "hello"}])
    s2 = store.get_or_create("u:ou_a", "ou_a", "dm")
    assert s2.session_id == s1.session_id
    assert s2.messages == [{"role": "user", "content": "hello"}]


def test_clear_removes_session(tmp_path: Path):
    """clear 后重建为空会话。"""
    store = FeishuSessionStore(data_dir=tmp_path)
    s1 = store.get_or_create("u:ou_a", "ou_a", "dm")
    store.save(s1, [{"role": "user", "content": "x"}])
    store.clear("u:ou_a")
    s2 = store.get_or_create("u:ou_a", "ou_a", "dm")
    assert s2.messages == []
    assert s2.session_id != s1.session_id


def test_inject_replaces_messages(tmp_path: Path):
    """inject 用外部消息替换当前会话历史。"""
    store = FeishuSessionStore(data_dir=tmp_path)
    store.get_or_create("u:ou_a", "ou_a", "dm")
    external = [{"role": "user", "content": "old work"}]
    store.inject("u:ou_a", external)
    s = store.get_or_create("u:ou_a", "ou_a", "dm")
    assert s.messages == external


def test_save_then_load_persists_to_disk(tmp_path: Path):
    """save 写入磁盘，重新构造 store 能读回。"""
    store1 = FeishuSessionStore(data_dir=tmp_path)
    s1 = store1.get_or_create("u:ou_a", "ou_a", "dm")
    store1.save(s1, [{"role": "user", "content": "persisted"}])

    store2 = FeishuSessionStore(data_dir=tmp_path)
    s2 = store2.get_or_create("u:ou_a", "ou_a", "dm")
    assert s2.messages == [{"role": "user", "content": "persisted"}]


def test_set_and_get_model(tmp_path: Path):
    """会话模型可单独设置与读取。"""
    store = FeishuSessionStore(data_dir=tmp_path)
    store.get_or_create("u:ou_a", "ou_a", "dm")
    store.set_model("u:ou_a", "gpt-4o")
    s2 = store.get_or_create("u:ou_a", "ou_a", "dm")
    assert s2.model == "gpt-4o"
