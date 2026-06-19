"""微信适配器准入控制测试。"""
from __future__ import annotations

from illusion.channels.base import InboundMessage
from illusion.channels.config import WeixinChannelConfig
from illusion.channels.weixin.adapter import WeixinChannel


def _channel(allow_bots=False, bot_user_id="self_bot"):
    """构造 WeixinChannel 实例（仅测准入逻辑，不连接）。"""
    cfg = WeixinChannelConfig(enabled=True, allow_bots=allow_bots, user_id=bot_user_id)
    ch = WeixinChannel.__new__(WeixinChannel)  # 跳过 __init__ 避免连接
    ch.config = cfg
    ch._user_id = bot_user_id
    ch._context_tokens = {}
    return ch


def _msg(user_id="wx_user", chat_type="dm", is_bot=False):
    """构造入站消息。"""
    return InboundMessage(
        text="hi", chat_id=user_id, chat_type=chat_type,
        user_id=user_id, user_name="u", message_id="om_1", is_bot=is_bot,
    )


def test_admit_self_echo_rejected():
    """自回显被拒。"""
    ch = _channel(bot_user_id="self_bot")
    assert ch._admit(_msg(user_id="self_bot")) is False


def test_admit_other_bot_rejected():
    """allow_bots=False 时其他机器人被拒。"""
    ch = _channel(allow_bots=False)
    assert ch._admit(_msg(user_id="other_bot", is_bot=True)) is False


def test_admit_dm_allowed():
    """私聊放行。"""
    ch = _channel()
    assert ch._admit(_msg(user_id="wx_user", chat_type="dm")) is True


def test_admit_group_rejected():
    """群消息直接丢弃（bot 身份限制）。"""
    ch = _channel()
    assert ch._admit(_msg(user_id="wx_user", chat_type="group")) is False


def test_admit_bot_allowed_when_enabled():
    """allow_bots=True 时机器人放行。"""
    ch = _channel(allow_bots=True)
    assert ch._admit(_msg(user_id="other_bot", is_bot=True)) is True


def test_normalize_extracts_context_token():
    """_normalize 从入站消息提取 context_token 并缓存。"""
    ch = _channel()
    raw_msg = {
        "from_user_id": "wx_user",
        "context_token": "ctx_tok_123",
        "item_list": [{"type": 1, "text_item": {"text": "你好"}}],
        "msgid": "msg_001",
    }
    msg = ch._normalize(raw_msg)
    assert msg is not None
    assert msg.text == "你好"
    assert msg.user_id == "wx_user"
    assert ch._context_tokens.get("wx_user") == "ctx_tok_123"


def test_normalize_returns_none_for_empty_user():
    """from_user_id 为空时返回 None。"""
    ch = _channel()
    msg = ch._normalize({"from_user_id": "", "item_list": []})
    assert msg is None


def test_normalize_extracts_text_from_item_list():
    """从 item_list 的 type=1 项提取文本。"""
    ch = _channel()
    raw_msg = {
        "from_user_id": "wx_user",
        "item_list": [
            {"type": 99, "text_item": {"text": "ignored"}},
            {"type": 1, "text_item": {"text": "实际文本"}},
        ],
        "msgid": "msg_002",
    }
    msg = ch._normalize(raw_msg)
    assert msg is not None
    assert msg.text == "实际文本"
