"""渠道注册表测试

验证 ChannelRegistry 正确注册三个内置渠道，
并能按名称查询描述符。
"""
from __future__ import annotations

from illusion.channels.registry import ChannelDescriptor, ChannelRegistry


def test_registry_has_three_channels():
    """注册表应包含 feishu/weixin/qq 三个内置渠道"""
    descriptors = ChannelRegistry.all_descriptors()
    names = {d.name for d in descriptors}
    assert names == {"feishu", "weixin", "qq"}


def test_registry_get_by_name():
    """按名称查询应返回正确的描述符"""
    desc = ChannelRegistry.get("feishu")
    assert desc is not None
    assert desc.name == "feishu"
    assert desc.config_attr == "feishu"
    assert "lark_oapi" in desc.dependencies


def test_registry_get_unknown_returns_none():
    """查询未知渠道名应返回 None"""
    assert ChannelRegistry.get("unknown") is None
    assert ChannelRegistry.get("") is None
