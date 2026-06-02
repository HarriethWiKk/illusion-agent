"""LSP 客户端测试。"""

from __future__ import annotations

import json

import pytest

from illusion.services.lsp.client import LspClient, decode_message, encode_message


class TestEncodeMessage:
    """JSON-RPC 消息编码测试。"""

    def test_encode_request(self):
        msg = encode_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert b"Content-Length:" in msg
        header, body = msg.split(b"\r\n\r\n", 1)
        content_length = int(header.split(b":")[1].strip())
        assert content_length == len(body)
        parsed = json.loads(body)
        assert parsed["method"] == "initialize"
        assert parsed["id"] == 1

    def test_encode_notification(self):
        msg = encode_message({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        header, body = msg.split(b"\r\n\r\n", 1)
        parsed = json.loads(body)
        assert "id" not in parsed
        assert parsed["method"] == "initialized"


class TestDecodeMessage:
    """JSON-RPC 消息解码测试。"""

    def test_decode_single_message(self):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}).encode()
        header = f"Content-Length: {len(body)}\r\n\r\n".encode()
        data = header + body

        messages, remaining = decode_message(data)
        assert len(messages) == 1
        assert messages[0]["id"] == 1
        assert messages[0]["result"] == {}
        assert remaining == b""

    def test_decode_multiple_messages(self):
        body1 = json.dumps({"jsonrpc": "2.0", "id": 1, "result": "a"}).encode()
        body2 = json.dumps({"jsonrpc": "2.0", "id": 2, "result": "b"}).encode()
        data = (
            f"Content-Length: {len(body1)}\r\n\r\n".encode() + body1
            + f"Content-Length: {len(body2)}\r\n\r\n".encode() + body2
        )

        messages, remaining = decode_message(data)
        assert len(messages) == 2
        assert messages[0]["result"] == "a"
        assert messages[1]["result"] == "b"
        assert remaining == b""

    def test_decode_incomplete_message(self):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}).encode()
        header = f"Content-Length: {len(body)}\r\n\r\n".encode()
        data = header + body[: len(body) // 2]

        messages, remaining = decode_message(data)
        assert len(messages) == 0
        assert remaining == data

    def test_decode_no_content_length(self):
        data = b"garbage data\r\n\r\nbody"
        messages, remaining = decode_message(data)
        assert len(messages) == 0


class TestLspClient:
    """LspClient 生命周期测试。"""

    @pytest.mark.asyncio
    async def test_client_starts_uninitialized(self):
        client = LspClient()
        assert not client.is_initialized
        assert client.capabilities is None

    @pytest.mark.asyncio
    async def test_request_without_start_raises(self):
        client = LspClient()
        with pytest.raises(RuntimeError, match="not started"):
            await client.request("textDocument/definition", {})
