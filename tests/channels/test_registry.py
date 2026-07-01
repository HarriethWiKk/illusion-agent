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


def test_config_has_enabled_channels_uses_registry():
    """has_enabled_channels 遍历 registry 而非硬编码字段"""
    from illusion.channels.config import ChannelsConfig, FeishuChannelConfig

    # 全部禁用
    empty = ChannelsConfig()
    assert empty.has_enabled_channels() is False

    # 仅飞书启用
    feishu_only = ChannelsConfig(feishu=FeishuChannelConfig(enabled=True, app_id="x"))
    assert feishu_only.has_enabled_channels() is True

    # 仅微信启用
    from illusion.channels.config import WeixinChannelConfig
    weixin_only = ChannelsConfig(weixin=WeixinChannelConfig(enabled=True))
    assert weixin_only.has_enabled_channels() is True

    # 仅 QQ 启用
    from illusion.channels.config import QQChannelConfig
    qq_only = ChannelsConfig(qq=QQChannelConfig(enabled=True))
    assert qq_only.has_enabled_channels() is True


def test_config_enabled_channel_names_uses_registry():
    """enabled_channel_names 遍历 registry 返回已启用渠道名"""
    from illusion.channels.config import (
        ChannelsConfig,
        FeishuChannelConfig,
        QQChannelConfig,
        WeixinChannelConfig,
    )

    empty = ChannelsConfig()
    assert empty.enabled_channel_names() == []

    all_enabled = ChannelsConfig(
        feishu=FeishuChannelConfig(enabled=True, app_id="x"),
        weixin=WeixinChannelConfig(enabled=True),
        qq=QQChannelConfig(enabled=True),
    )
    names = set(all_enabled.enabled_channel_names())
    assert names == {"feishu", "weixin", "qq"}


def test_serve_dependency_check_uses_registry(monkeypatch):
    """serve.py 依赖检查应遍历 registry 的 dependencies 字段

    验证：当 feishu 启用但 lark_oapi 不可用时，
    依赖检查使用 registry 中注册的 dependencies。
    """
    import builtins

    # 模拟 lark_oapi 不可用
    real_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "lark_oapi":
            raise ImportError("No module named 'lark_oapi'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)

    from illusion.channels.config import ChannelsConfig, FeishuChannelConfig
    from illusion.channels import serve

    cfg = ChannelsConfig(feishu=FeishuChannelConfig(enabled=True, app_id="x"))

    # 捕获 print 输出
    import io
    from contextlib import redirect_stdout

    captured = io.StringIO()
    with redirect_stdout(captured):
        serve._check_channel_dependencies(cfg)

    output = captured.getvalue()
    # 应提示 feishu 依赖缺失
    assert "feishu" in output.lower() or "lark" in output.lower()
