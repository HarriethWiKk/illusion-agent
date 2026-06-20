"""QQ 渠道单元测试"""
from illusion.channels.config import (
    QQChannelConfig, QQGroupPolicy, ChannelsConfig,
    load_channels_config, save_channels_config,
)


class TestQQChannelConfig:
    """QQChannelConfig 模型测试"""

    def test_default_values(self):
        """默认值：未启用，空凭据"""
        cfg = QQChannelConfig()
        assert cfg.enabled is False
        assert cfg.app_id == ""
        assert cfg.client_secret == ""
        assert cfg.allow_bots is False
        assert cfg.group_sessions_per_user is True
        assert cfg.require_mention is True

    def test_group_policy_default(self):
        """群组策略默认 open"""
        cfg = QQChannelConfig()
        assert cfg.group_policy.mode == "open"
        assert cfg.group_policy.allowlist == []
        assert cfg.group_policy.blacklist == []
        assert cfg.group_policy.admin_list == []

    def test_roundtrip(self):
        """序列化/反序列化保持一致"""
        cfg = QQChannelConfig(
            enabled=True,
            app_id="test_id",
            client_secret="test_secret",
            group_policy=QQGroupPolicy(mode="allowlist", allowlist=["g1"]),
        )
        data = cfg.model_dump()
        restored = QQChannelConfig.model_validate(data)
        assert restored.app_id == "test_id"
        assert restored.group_policy.mode == "allowlist"
        assert restored.group_policy.allowlist == ["g1"]


class TestChannelsConfigWithQQ:
    """ChannelsConfig 包含 QQ 字段"""

    def test_has_qq_field(self):
        cfg = ChannelsConfig()
        assert hasattr(cfg, "qq")
        assert isinstance(cfg.qq, QQChannelConfig)

    def test_has_enabled_channels_includes_qq(self):
        cfg = ChannelsConfig()
        cfg.qq.enabled = True
        cfg.qq.app_id = "test"
        assert cfg.has_enabled_channels() is True

    def test_enabled_channel_names_includes_qq(self):
        cfg = ChannelsConfig()
        cfg.qq.enabled = True
        names = cfg.enabled_channel_names()
        assert "qq" in names

    def test_roundtrip_with_qq(self, tmp_path):
        """完整 channels.json 含 QQ 配置的读写"""
        path = tmp_path / "channels.json"
        cfg = ChannelsConfig()
        cfg.qq = QQChannelConfig(enabled=True, app_id="abc", client_secret="xyz")
        save_channels_config(cfg, config_path=path)

        loaded = load_channels_config(config_path=path)
        assert loaded.qq.enabled is True
        assert loaded.qq.app_id == "abc"
        assert loaded.qq.client_secret == "xyz"
