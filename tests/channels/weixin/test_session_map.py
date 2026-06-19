"""微信会话存储测试。"""
from __future__ import annotations

from pathlib import Path

from illusion.channels.base import InboundMessage
from illusion.channels.weixin.session_map import WeixinSession, WeixinSessionStore


def _msg(chat_id: str, user_id: str) -> InboundMessage:
    """构造测试用入站消息。"""
    return InboundMessage(
        text="hi", chat_id=chat_id, chat_type="dm",
        user_id=user_id, user_name="tester", message_id="om_1",
    )


def test_build_session_key_dm(tmp_path: Path):
    """私聊按用户隔离。"""
    store = WeixinSessionStore(data_dir=tmp_path)
    assert store.build_session_key(_msg("wx_a", "wx_a")) == "u:wx_a"


def test_get_or_create_new(tmp_path: Path):
    """新 key 创建空会话。"""
    store = WeixinSessionStore(data_dir=tmp_path)
    session = store.get_or_create("u:wx_a", "wx_a", "dm")
    assert isinstance(session, WeixinSession)
    assert session.messages == []
    assert session.session_id


def test_save_and_load_roundtrip(tmp_path: Path):
    """保存后能读回。"""
    store = WeixinSessionStore(data_dir=tmp_path)
    s1 = store.get_or_create("u:wx_a", "wx_a", "dm")
    store.save(s1, [{"role": "user", "content": "hello"}])
    s2 = store.get_or_create("u:wx_a", "wx_a", "dm")
    assert s2.messages == [{"role": "user", "content": "hello"}]


def test_clear_removes_session(tmp_path: Path):
    """clear 后重建为空。"""
    store = WeixinSessionStore(data_dir=tmp_path)
    s1 = store.get_or_create("u:wx_a", "wx_a", "dm")
    store.save(s1, [{"role": "user", "content": "x"}])
    store.clear("u:wx_a")
    s2 = store.get_or_create("u:wx_a", "wx_a", "dm")
    assert s2.messages == []


def test_set_and_get_model(tmp_path: Path):
    """会话模型可设置与读取。"""
    store = WeixinSessionStore(data_dir=tmp_path)
    store.get_or_create("u:wx_a", "wx_a", "dm")
    store.set_model("u:wx_a", "gpt-4o")
    s = store.get_or_create("u:wx_a", "wx_a", "dm")
    assert s.model == "gpt-4o"
