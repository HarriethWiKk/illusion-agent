"""QQ 渠道单元测试"""
from unittest.mock import MagicMock

from illusion.channels.base import InboundMessage
from illusion.channels.config import (
    QQChannelConfig, QQGroupPolicy, ChannelsConfig,
    load_channels_config, save_channels_config,
)
from illusion.channels.qq.adapter import QQChannel
from illusion.channels.qq.api import split_text, strip_markdown, _build_text_body
from illusion.channels.qq.session_map import QQSession, QQSessionStore


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


class TestSplitText:
    """文本分片测试（代码块感知 + 分片编号）"""

    def test_short_text_no_split(self):
        assert split_text("hello") == ["hello"]

    def test_split_at_newline(self):
        text = "a" * 1000 + "\n\n" + "b" * 1000
        chunks = split_text(text, max_length=2000)
        assert len(chunks) == 2
        # 多分片带编号
        assert "(1/2)" in chunks[0]
        assert "(2/2)" in chunks[1]

    def test_respects_max_length(self):
        text = "x" * 5000
        chunks = split_text(text, max_length=4000)
        # 去掉编号后检查长度
        for c in chunks:
            content = c.rsplit("\n\n(", 1)[0] if "\n\n(" in c else c
            assert len(content) <= 4000

    def test_code_block_awareness(self):
        """代码块内分片时自动闭合/重开围栏"""
        code = "```python\n" + "x = 1\n" * 500 + "```"
        chunks = split_text(code, max_length=2000)
        assert len(chunks) >= 2
        # 去掉编号后检查围栏处理
        first_content = chunks[0].rsplit("\n\n(", 1)[0]
        second_content = chunks[1].split("\n\n(", 1)[0]
        # 第一片应在代码块内闭合
        assert first_content.rstrip().endswith("```")
        # 第二片应重开围栏
        assert second_content.startswith("```python")

    def test_no_code_block_normal_split(self):
        """无代码块时正常分片"""
        text = "hello world " * 500
        chunks = split_text(text, max_length=2000)
        assert len(chunks) >= 2
        # 不应包含代码围栏
        for c in chunks:
            assert "```" not in c


class TestStripMarkdown:
    """Markdown 剥离测试"""

    def test_bold(self):
        assert strip_markdown("**hello**") == "hello"

    def test_italic(self):
        assert strip_markdown("*world*") == "world"

    def test_code_block(self):
        text = "```python\ncode\n```"
        result = strip_markdown(text)
        assert "```" not in result
        assert "code" in result

    def test_inline_code(self):
        assert strip_markdown("`foo`") == "foo"

    def test_heading(self):
        assert strip_markdown("## Title") == "Title"

    def test_link(self):
        assert strip_markdown("[text](url)") == "text"


class TestBuildTextBody:
    """消息请求体构建测试"""

    def test_markdown_envelope(self):
        """markdown 模式使用 msg_type=2 信封"""
        body = _build_text_body("hello", markdown=True)
        assert body["msg_type"] == 2
        assert body["markdown"]["content"] == "hello"
        assert "msg_seq" in body
        assert "msg_id" not in body  # msg_id 由调用方补充

    def test_text_mode(self):
        """纯文本模式使用 msg_type=0"""
        body = _build_text_body("hello", markdown=False)
        assert body["msg_type"] == 0
        assert body["content"] == "hello"
        assert "msg_seq" in body

    def test_truncation(self):
        """超长内容截断到 MAX_MESSAGE_LENGTH"""
        long_text = "x" * 5000
        body = _build_text_body(long_text, markdown=True)
        assert len(body["markdown"]["content"]) == 4000


class TestQQSessionStore:
    """QQSessionStore 测试"""

    def _make_msg(self, chat_id="c1", user_id="u1", chat_type="dm") -> InboundMessage:
        return InboundMessage(
            text="hi", chat_id=chat_id, chat_type=chat_type,
            user_id=user_id, user_name="test", message_id="m1",
        )

    def test_build_key_dm(self, tmp_path):
        store = QQSessionStore(tmp_path)
        msg = self._make_msg(chat_type="dm")
        assert store.build_session_key(msg) == "c1"

    def test_build_key_group_isolated(self, tmp_path):
        store = QQSessionStore(tmp_path, group_sessions_per_user=True)
        msg = self._make_msg(chat_id="g1", user_id="u1", chat_type="group")
        assert store.build_session_key(msg) == "g1_u1"

    def test_build_key_group_shared(self, tmp_path):
        store = QQSessionStore(tmp_path, group_sessions_per_user=False)
        msg = self._make_msg(chat_id="g1", user_id="u1", chat_type="group")
        assert store.build_session_key(msg) == "g1"

    def test_get_or_create_new(self, tmp_path):
        store = QQSessionStore(tmp_path)
        session = store.get_or_create("key1", "u1", "dm")
        assert session.key == "key1"
        assert session.messages == []

    def test_save_and_load(self, tmp_path):
        store = QQSessionStore(tmp_path)
        session = store.get_or_create("key1", "u1", "dm")
        msgs = [{"role": "user", "content": "hello"}]
        store.save(session, msgs)

        loaded = store.get_or_create("key1", "u1", "dm")
        assert loaded.messages == msgs


class TestQQChannelNormalize:
    """QQChannel._normalize 测试"""

    def _make_channel(self) -> QQChannel:
        config = MagicMock()
        config.app_id = "test_id"
        config.client_secret = "test_secret"
        config.allow_bots = False
        config.require_mention = True
        config.group_sessions_per_user = True
        config.group_policy = MagicMock()
        config.group_policy.mode = "open"
        config.group_policy.allowlist = []
        config.group_policy.blacklist = []
        config.group_policy.admin_list = []
        settings = MagicMock()
        return QQChannel(config, settings)

    def test_normalize_c2c(self):
        ch = self._make_channel()
        raw = {
            "id": "msg_001",
            "content": "  hello world  ",
            "author": {"id": "user_openid_123", "username": "TestUser"},
        }
        msg = ch._normalize_c2c(raw)
        assert msg is not None
        assert msg.text == "hello world"
        assert msg.chat_type == "dm"
        assert msg.user_id == "user_openid_123"
        assert msg.user_name == "TestUser"
        assert msg.message_id == "msg_001"

    def test_normalize_group(self):
        ch = self._make_channel()
        raw = {
            "id": "msg_002",
            "content": "<@!bot_openid> help me",
            "author": {"id": "user_openid_456", "username": "GroupUser"},
            "group_openid": "group_openid_789",
            "mentions": [{"id": "bot_openid", "username": "MyBot"}],
        }
        msg = ch._normalize_group(raw)
        assert msg is not None
        assert msg.text == "help me"
        assert msg.chat_type == "group"
        assert msg.chat_id == "group_openid_789"
        assert msg.user_id == "user_openid_456"

    def test_normalize_c2c_missing_fields(self):
        ch = self._make_channel()
        raw = {"id": "msg_003"}
        msg = ch._normalize_c2c(raw)
        assert msg is None


class TestQQChannelAdmit:
    """QQChannel._admit 测试"""

    def _make_msg(self, **kwargs):
        defaults = {
            "text": "hi", "chat_id": "c1", "chat_type": "dm",
            "user_id": "u1", "user_name": "test", "message_id": "m1",
            "is_bot": False,
        }
        defaults.update(kwargs)
        return InboundMessage(**defaults)

    def _make_channel(self, allow_bots=False):
        config = MagicMock()
        config.app_id = "bot_id"
        config.allow_bots = allow_bots
        config.group_policy = MagicMock()
        config.group_policy.mode = "open"
        config.group_policy.allowlist = []
        config.group_policy.blacklist = []
        config.group_policy.admin_list = []
        settings = MagicMock()
        ch = QQChannel(config, settings)
        ch._bot_openid = "bot_id"
        return ch

    def test_self_echo_rejected(self):
        ch = self._make_channel()
        msg = self._make_msg(user_id="bot_id")
        assert ch._admit(msg) is False

    def test_bot_rejected_when_disabled(self):
        ch = self._make_channel(allow_bots=False)
        msg = self._make_msg(is_bot=True)
        assert ch._admit(msg) is False

    def test_bot_allowed_when_enabled(self):
        ch = self._make_channel(allow_bots=True)
        msg = self._make_msg(is_bot=True)
        assert ch._admit(msg) is True

    def test_normal_dm_allowed(self):
        ch = self._make_channel()
        msg = self._make_msg()
        assert ch._admit(msg) is True

    def test_group_policy_disabled(self):
        ch = self._make_channel()
        ch.config.group_policy.mode = "disabled"
        msg = self._make_msg(chat_type="group")
        assert ch._admit(msg) is False

    def test_group_policy_allowlist(self):
        ch = self._make_channel()
        ch.config.group_policy.mode = "allowlist"
        ch.config.group_policy.allowlist = ["g1"]
        msg_allowed = self._make_msg(chat_type="group", chat_id="g1")
        msg_blocked = self._make_msg(chat_type="group", chat_id="g2")
        assert ch._admit(msg_allowed) is True
        assert ch._admit(msg_blocked) is False

    def test_group_policy_blacklist(self):
        ch = self._make_channel()
        ch.config.group_policy.mode = "blacklist"
        ch.config.group_policy.blacklist = ["g1"]
        msg_allowed = self._make_msg(chat_type="group", chat_id="g2")
        msg_blocked = self._make_msg(chat_type="group", chat_id="g1")
        assert ch._admit(msg_allowed) is True
        assert ch._admit(msg_blocked) is False

    def test_admin_always_passes(self):
        ch = self._make_channel()
        ch.config.group_policy.mode = "disabled"
        ch.config.group_policy.admin_list = ["admin_user"]
        msg = self._make_msg(chat_type="group", user_id="admin_user")
        assert ch._admit(msg) is True
