# tests/channels/test_health_probe.py
"""渠道 health_probe 测试"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_default_health_probe_returns_true():
    """默认 health_probe 返回 True"""
    from illusion.channels.base import Channel

    channel = MagicMock(spec=Channel)
    channel.health_probe = Channel.health_probe.__get__(channel, Channel)
    result = await channel.health_probe()
    assert result is True


@pytest.mark.asyncio
async def test_feishu_health_probe_success(monkeypatch: pytest.MonkeyPatch):
    """飞书 health_probe 成功（bot_info API 调用成功）"""
    from illusion.channels.feishu.adapter import FeishuChannel
    from illusion.channels.config import FeishuChannelConfig

    cfg = FeishuChannelConfig(enabled=True, app_id="test_id", app_secret="test_secret")
    channel = FeishuChannel.__new__(FeishuChannel)
    channel.config = cfg
    channel._client = MagicMock()

    # 模拟 bot_info.get 返回成功响应
    fake_resp = MagicMock()
    fake_resp.success.return_value = True
    fake_resp.data = MagicMock()
    fake_resp.data.bot = MagicMock(open_id="ou_test")
    channel._client.im.v1.bot_info.get = MagicMock(return_value=fake_resp)

    result = await channel.health_probe()
    assert result is True


@pytest.mark.asyncio
async def test_feishu_health_probe_failure(monkeypatch: pytest.MonkeyPatch):
    """飞书 health_probe 失败（API 调用抛异常）"""
    from illusion.channels.feishu.adapter import FeishuChannel
    from illusion.channels.config import FeishuChannelConfig

    cfg = FeishuChannelConfig(enabled=True, app_id="test_id", app_secret="test_secret")
    channel = FeishuChannel.__new__(FeishuChannel)
    channel.config = cfg
    channel._client = MagicMock()

    # 模拟 bot_info.get 抛异常（网络不可达）
    channel._client.im.v1.bot_info.get = MagicMock(side_effect=ConnectionError("网络不可达"))

    result = await channel.health_probe()
    assert result is False


@pytest.mark.asyncio
async def test_feishu_health_probe_no_client():
    """飞书 health_probe 在 _client 为 None 时返回 False"""
    from illusion.channels.feishu.adapter import FeishuChannel
    from illusion.channels.config import FeishuChannelConfig

    cfg = FeishuChannelConfig(enabled=True, app_id="test_id", app_secret="test_secret")
    channel = FeishuChannel.__new__(FeishuChannel)
    channel.config = cfg
    channel._client = None

    result = await channel.health_probe()
    assert result is False
