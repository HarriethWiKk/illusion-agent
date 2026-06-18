"""飞书适配器准入控制测试。"""
from __future__ import annotations

from illusion.channels.base import InboundMessage
from illusion.channels.config import FeishuChannelConfig, FeishuGroupPolicy
from illusion.channels.feishu.adapter import FeishuChannel


def _channel(allow_bots=False, require_mention=True, policy_mode="open",
             allowlist=None, blacklist=None, admin_list=None, bot_id="ou_bot"):
    """构造 FeishuChannel 实例（仅测准入逻辑，不连接）。"""
    cfg = FeishuChannelConfig(
        enabled=True, app_id="cli", app_secret="s",
        allow_bots=allow_bots, require_mention=require_mention,
        group_policy=FeishuGroupPolicy(
            mode=policy_mode, allowlist=allowlist or [],
            blacklist=blacklist or [], admin_list=admin_list or [],
        ),
    )
    ch = FeishuChannel.__new__(FeishuChannel)  # 跳过 __init__ 避免连接
    ch.config = cfg
    ch._bot_open_id = bot_id  # 模拟已 hydrate 的 bot ID
    return ch


def _msg(user_id="ou_user", chat_type="dm", is_bot=False, text="hi",
         chat_id="ou_user", mentioned_bot=False):
    """构造入站消息及 @bot 标志。"""
    msg = InboundMessage(
        text=text, chat_id=chat_id, chat_type=chat_type,
        user_id=user_id, user_name="u", message_id="om_1", is_bot=is_bot,
    )
    return msg, mentioned_bot


def test_admit_self_echo_rejected():
    """自回显（发送者是 bot 自身）被拒。"""
    ch = _channel()
    msg, _ = _msg(user_id="ou_bot")  # 发送者 == bot
    assert ch._admit(msg, mentioned_bot=False) is False


def test_admit_other_bot_rejected_when_disallowed():
    """allow_bots=False 时其他机器人被拒。"""
    ch = _channel(allow_bots=False)
    msg, _ = _msg(user_id="ou_other_bot", is_bot=True)
    assert ch._admit(msg, mentioned_bot=False) is False


def test_admit_other_bot_allowed_when_enabled():
    """allow_bots=True 时其他机器人放行。"""
    ch = _channel(allow_bots=True)
    msg, _ = _msg(user_id="ou_other_bot", is_bot=True)
    assert ch._admit(msg, mentioned_bot=False) is True


def test_admit_dm_always_allowed():
    """私聊（非 bot 非 self）放行。"""
    ch = _channel()
    msg, _ = _msg(user_id="ou_user", chat_type="dm")
    assert ch._admit(msg, mentioned_bot=False) is True


def test_admit_group_require_mention_rejected_without_mention():
    """群组 require_mention=True 但未 @bot 时被拒。"""
    ch = _channel(require_mention=True)
    msg, _ = _msg(user_id="ou_user", chat_type="group", chat_id="oc_room")
    assert ch._admit(msg, mentioned_bot=False) is False


def test_admit_group_require_mention_allowed_with_mention():
    """群组 require_mention=True 且 @bot 时放行。"""
    ch = _channel(require_mention=True)
    msg, _ = _msg(user_id="ou_user", chat_type="group", chat_id="oc_room")
    assert ch._admit(msg, mentioned_bot=True) is True


def test_admit_group_policy_disabled():
    """群组策略 mode=disabled 全拒。"""
    ch = _channel(policy_mode="disabled")
    msg, _ = _msg(user_id="ou_user", chat_type="group", chat_id="oc_room")
    assert ch._admit(msg, mentioned_bot=True) is False


def test_admit_group_policy_allowlist():
    """群组策略 mode=allowlist 仅白名单放行。"""
    ch = _channel(policy_mode="allowlist", allowlist=["oc_allowed"])
    msg_ok, _ = _msg(user_id="ou_user", chat_type="group", chat_id="oc_allowed")
    msg_no, _ = _msg(user_id="ou_user", chat_type="group", chat_id="oc_blocked")
    assert ch._admit(msg_ok, mentioned_bot=True) is True
    assert ch._admit(msg_no, mentioned_bot=True) is False


def test_admit_group_policy_blacklist():
    """群组策略 mode=blacklist 黑名单外放行。"""
    ch = _channel(policy_mode="blacklist", blacklist=["oc_blocked"])
    msg_ok, _ = _msg(user_id="ou_user", chat_type="group", chat_id="oc_ok")
    msg_no, _ = _msg(user_id="ou_user", chat_type="group", chat_id="oc_blocked")
    assert ch._admit(msg_ok, mentioned_bot=True) is True
    assert ch._admit(msg_no, mentioned_bot=True) is False


def test_admit_group_admin_always_allowed():
    """管理员 user_id 永远放行（即使群组策略禁止）。"""
    ch = _channel(policy_mode="disabled", admin_list=["ou_admin"])
    msg, _ = _msg(user_id="ou_admin", chat_type="group", chat_id="oc_room")
    assert ch._admit(msg, mentioned_bot=False) is True


def test_admit_dm_not_affected_by_group_policy():
    """私聊不受群组策略影响。"""
    ch = _channel(policy_mode="disabled")
    msg, _ = _msg(user_id="ou_user", chat_type="dm")
    assert ch._admit(msg, mentioned_bot=False) is True
