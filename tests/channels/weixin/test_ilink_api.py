"""iLink Bot API 客户端测试（纯逻辑，不依赖 aiohttp）。"""
from __future__ import annotations

from illusion.channels.weixin.ilink_api import (
    ILINK_APP_CLIENT_VERSION,
    MAX_MESSAGE_LENGTH,
    MSG_STATE_FINISH,
    MSG_TYPE_BOT,
    TYPING_START,
    TYPING_STOP,
    WeixinCredentials,
    _build_headers,
    _split_text,
)


def test_build_headers_has_auth():
    """请求头包含 Bearer token 和 iLink 标识。"""
    headers = _build_headers(token="test_token_123")
    assert headers["Authorization"] == "Bearer test_token_123"
    assert headers["iLink-App-Id"] == "bot"
    assert headers["iLink-App-ClientVersion"] == str(ILINK_APP_CLIENT_VERSION)
    assert "X-WECHAT-UIN" in headers


def test_build_headers_random_uin():
    """每次调用 X-WECHAT-UIN 不同。"""
    h1 = _build_headers(token="t")
    h2 = _build_headers(token="t")
    assert h1["X-WECHAT-UIN"] != h2["X-WECHAT-UIN"]


def test_split_text_short():
    """短文本不分片。"""
    assert _split_text("hello", 2000) == ["hello"]


def test_split_text_long():
    """长文本按段落分片。"""
    para = "a" * 1500
    text = f"{para}\n\n{para}"
    chunks = _split_text(text, 2000)
    assert len(chunks) == 2
    assert all(len(c) <= 2000 for c in chunks)


def test_split_text_preserves_paragraphs():
    """分片不在段落中间断。"""
    para1 = "b" * 1900
    para2 = "c" * 100
    text = f"{para1}\n\n{para2}"
    chunks = _split_text(text, 2000)
    assert len(chunks) == 2
    assert para1 in chunks[0]
    assert para2 in chunks[1]


def test_weixin_credentials_dataclass():
    """凭据数据类正确构造。"""
    creds = WeixinCredentials(
        account_id="bot@im.bot",
        token="tok",
        base_url="https://ilinkai.weixin.qq.com",
        user_id="u123",
    )
    assert creds.account_id == "bot@im.bot"
    assert creds.token == "tok"
    assert creds.base_url == "https://ilinkai.weixin.qq.com"
    assert creds.user_id == "u123"


def test_constants_correct():
    """核心常量值正确。"""
    assert MAX_MESSAGE_LENGTH == 2000
    assert MSG_TYPE_BOT == 2
    assert MSG_STATE_FINISH == 2
    assert TYPING_START == 1
    assert TYPING_STOP == 2
    assert ILINK_APP_CLIENT_VERSION == (2 << 16) | (2 << 8) | 0
