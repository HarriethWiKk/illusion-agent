"""投递解析测试"""
from illusion.channels.delivery import parse_deliver_to


def test_parse_empty():
    """空字符串返回 None"""
    assert parse_deliver_to("") is None


def test_parse_channel_with_chat_id():
    """渠道名:chat_id 格式（显式 chat_id 优先级最高）"""
    assert parse_deliver_to("feishu:oc_456") == ("feishu", "oc_456")


def test_parse_qq_format():
    """QQ 渠道格式"""
    assert parse_deliver_to("qq:group_123") == ("qq", "group_123")


def test_parse_weixin_format():
    """微信渠道格式"""
    assert parse_deliver_to("weixin:wxid_abc") == ("weixin", "wxid_abc")


def test_parse_feishu_open_id():
    """飞书用户 open_id 格式"""
    assert parse_deliver_to("feishu:ou_xxx") == ("feishu", "ou_xxx")


def test_parse_invalid_format():
    """deliver_to 含冒号但缺 channel 或 chat_id → None"""
    assert parse_deliver_to("feishu:") is None
    assert parse_deliver_to(":oc_123") is None


def test_parse_channel_only_with_chat_id():
    """仅渠道名 + chat_id 有值 → 用 chat_id 回投来源会话"""
    assert parse_deliver_to("feishu", "oc_origin") == ("feishu", "oc_origin")


def test_parse_channel_only_without_chat_id():
    """仅渠道名 + chat_id 为空 → None（LLM 应填完整 ID）"""
    assert parse_deliver_to("feishu") is None


def test_parse_channel_only_with_empty_chat_id():
    """仅渠道名 + chat_id 空串 → None"""
    assert parse_deliver_to("qq", "") is None


def test_parse_explicit_chat_id_overrides_origin():
    """显式 chat_id（含冒号）优先于 origin chat_id"""
    assert parse_deliver_to("feishu:oc_explicit", "oc_origin") == ("feishu", "oc_explicit")


def test_parse_unknown_channel_with_chat_id():
    """未知渠道名 + chat_id → 仍返回（渠道名校验在 deliver_to_channel 中）"""
    assert parse_deliver_to("unknown:xxx") == ("unknown", "xxx")


def test_parse_unknown_channel_without_chat_id():
    """未知渠道名 + 无 chat_id → None"""
    assert parse_deliver_to("unknown") is None


def test_parse_strips_whitespace_around_channel_and_chat_id():
    """LLM 输出常在冒号后带空格，应 strip 两端空白"""
    assert parse_deliver_to("feishu: oc_456") == ("feishu", "oc_456")
    assert parse_deliver_to(" feishu : ou_xxx ") == ("feishu", "ou_xxx")
    assert parse_deliver_to("qq:  group_123") == ("qq", "group_123")
