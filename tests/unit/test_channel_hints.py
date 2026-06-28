"""平台感知提示词测试"""
from illusion.prompts.channel_hints import get_channel_hint


def test_get_channel_hint_feishu():
    """飞书渠道提示词存在且非空"""
    hint = get_channel_hint("feishu")
    assert hint is not None
    assert "Feishu" in hint or "飞书" in hint
    assert "Markdown is supported" in hint
    assert len(hint) > 20


def test_get_channel_hint_qq_markdown_disabled():
    """QQ 渠道默认（markdown 关闭）提示词"""
    hint = get_channel_hint("qq")
    assert hint is not None
    assert "QQ" in hint
    assert "Markdown is NOT supported" in hint
    assert "plain text" in hint


def test_get_channel_hint_qq_markdown_enabled():
    """QQ 渠道 markdown 开启时提示词"""
    hint = get_channel_hint("qq", qq_markdown_support=True)
    assert hint is not None
    assert "QQ" in hint
    assert "Markdown is supported" in hint
    assert "msg_type=2" in hint


def test_get_channel_hint_qq_markdown_explicit_false():
    """QQ 渠道显式 markdown_support=False"""
    hint = get_channel_hint("qq", qq_markdown_support=False)
    assert hint is not None
    assert "Markdown is NOT supported" in hint


def test_get_channel_hint_weixin():
    """微信渠道提示词存在且非空"""
    hint = get_channel_hint("weixin")
    assert hint is not None
    assert "WeChat" in hint or "微信" in hint
    assert len(hint) > 20


def test_get_channel_hint_unknown():
    """未知渠道返回 None"""
    assert get_channel_hint("unknown_platform") is None
    assert get_channel_hint("") is None
