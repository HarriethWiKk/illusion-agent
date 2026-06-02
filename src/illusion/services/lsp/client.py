"""
LSP 客户端
==========

轻量级 JSON-RPC 2.0 over stdio 客户端，用于与外部 LSP 服务器通信。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# LSP 消息头分隔符
_HEADER_SEPARATOR = b"\r\n\r\n"
_CONTENT_LENGTH_PREFIX = b"Content-Length: "


def encode_message(body: dict[str, Any]) -> bytes:
    """将 JSON-RPC 消息编码为 LSP 带 Content-Length 头的字节序列。"""
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
    return header + payload


def decode_message(data: bytes) -> tuple[list[dict[str, Any]], bytes]:
    """从字节流中解码 JSON-RPC 消息。

    Returns:
        (已解码消息列表, 剩余未处理字节)
    """
    messages: list[dict[str, Any]] = []
    while data:
        # 查找 Content-Length 头
        idx = data.find(_CONTENT_LENGTH_PREFIX)
        if idx != 0:
            break

        header_end = data.find(_HEADER_SEPARATOR)
        if header_end == -1:
            break

        header_value = data[len(_CONTENT_LENGTH_PREFIX) : header_end].strip()
        try:
            content_length = int(header_value)
        except ValueError:
            break

        body_start = header_end + len(_HEADER_SEPARATOR)
        if len(data) < body_start + content_length:
            break  # 数据不完整

        body_bytes = data[body_start : body_start + content_length]
        try:
            messages.append(json.loads(body_bytes))
        except json.JSONDecodeError:
            pass

        data = data[body_start + content_length :]

    return messages, data


class LspClient:
    """单个 LSP 服务器的客户端连接。"""

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._notification_handlers: dict[str, list] = {}
        self._buffer: bytes = b""
        self._next_id: int = 1
        self.capabilities: dict[str, Any] | None = None
        self.is_initialized: bool = False

    async def start(self, command: str, args: list[str], options: dict[str, Any] | None = None) -> None:
        """启动 LSP 服务器子进程。"""
        if self._process is not None:
            raise RuntimeError("Client already started")

        self._process = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=options.get("env") if options else None,
        )
        self._reader_task = asyncio.create_task(self._read_loop())

    async def initialize(self, root_uri: str, capabilities: dict[str, Any] | None = None) -> dict[str, Any]:
        """发送 initialize 请求。"""
        params = {
            "processId": None,
            "rootUri": root_uri,
            "capabilities": capabilities or {},
        }
        result = await self.request("initialize", params)
        self.capabilities = result.get("capabilities", {})
        self.is_initialized = True
        await self.notify("initialized", {})
        return result

    async def request(self, method: str, params: Any, timeout: float = 30.0) -> Any:
        """发送请求并等待响应。"""
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("LSP client not started")

        msg_id = self._next_id
        self._next_id += 1

        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        msg = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
        self._process.stdin.write(encode_message(msg))
        await self._process.stdin.drain()

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"LSP request '{method}' timed out after {timeout}s")

        if "error" in response:
            error = response["error"]
            raise RuntimeError(f"LSP error: {error.get('message', error)}")

        return response.get("result")

    async def notify(self, method: str, params: Any) -> None:
        """发送通知（无需响应）。"""
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("LSP client not started")

        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        self._process.stdin.write(encode_message(msg))
        await self._process.stdin.drain()

    def on_notification(self, method: str, handler: Any) -> None:
        """注册通知处理器。"""
        self._notification_handlers.setdefault(method, []).append(handler)

    async def stop(self) -> None:
        """关闭连接并终止子进程。"""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except (ProcessLookupError, asyncio.TimeoutError):
                self._process.kill()
            self._process = None
        self.is_initialized = False

    async def _read_loop(self) -> None:
        """持续读取 stdout 并分发消息。"""
        assert self._process and self._process.stdout
        try:
            while True:
                chunk = await self._process.stdout.read(4096)
                if not chunk:
                    break
                self._buffer += chunk
                messages, self._buffer = decode_message(self._buffer)
                for msg in messages:
                    self._dispatch(msg)
        except asyncio.CancelledError:
            pass

    def _dispatch(self, msg: dict[str, Any]) -> None:
        """分发消息到对应的 future 或通知处理器。"""
        if "id" in msg and "method" not in msg:
            # 响应消息
            future = self._pending.pop(msg["id"], None)
            if future and not future.done():
                future.set_result(msg)
        elif "method" in msg:
            # 通知或请求
            handlers = self._notification_handlers.get(msg["method"], [])
            for handler in handlers:
                try:
                    handler(msg.get("params"))
                except Exception:
                    logger.exception("Notification handler error for %s", msg["method"])
