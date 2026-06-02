"""
LSP 客户端
==========

轻量级 JSON-RPC 2.0 over stdio 客户端，用于与外部 LSP 服务器通信。
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
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
            break

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
        self._stderr_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._notification_handlers: dict[str, list] = {}
        self._request_handlers: dict[str, Any] = {}  # 服务器->客户端请求处理器
        self._buffer: bytes = b""
        self._next_id: int = 1
        self._connected: bool = False
        self.capabilities: dict[str, Any] | None = None
        self.is_initialized: bool = False

    async def start(self, command: str, args: list[str], options: dict[str, Any] | None = None) -> None:
        """启动 LSP 服务器子进程。"""
        if self._process is not None:
            raise RuntimeError("Client already started")

        kwargs: dict[str, Any] = {
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }
        if options and options.get("env"):
            kwargs["env"] = options["env"]

        # Windows: 隐藏控制台窗口
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        self._process = await asyncio.create_subprocess_exec(
            command, *args, **kwargs,
        )
        self._connected = True
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._stderr_loop())

    async def initialize(
        self,
        root_uri: str,
        capabilities: dict[str, Any] | None = None,
        root_path: str | None = None,
        process_id: int | None = None,
        initialization_options: Any = None,
        workspace_folders: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """发送 initialize 请求。"""
        import os
        from pathlib import Path

        params: dict[str, Any] = {
            "processId": process_id or os.getpid(),
            "rootUri": root_uri,
            "capabilities": capabilities or {},
        }

        # 兼容性字段（某些旧服务器需要）
        if root_path:
            params["rootPath"] = root_path
        else:
            # 从 root_uri 推断 root_path
            if root_uri.startswith("file://"):
                uri_path = root_uri[7:]
                if len(uri_path) >= 2 and uri_path[0] == "/" and uri_path[2] == ":":
                    uri_path = uri_path[1:]
                params["rootPath"] = uri_path

        if initialization_options is not None:
            params["initializationOptions"] = initialization_options

        # LSP 3.16+ workspaceFolders
        if workspace_folders:
            params["workspaceFolders"] = workspace_folders
        else:
            params["workspaceFolders"] = [{
                "uri": root_uri,
                "name": Path(params.get("rootPath", "")).name or "workspace",
            }]
        result = await self.request("initialize", params)
        self.capabilities = result.get("capabilities", {})
        self.is_initialized = True
        await self.notify("initialized", {})
        return result

    async def request(self, method: str, params: Any, timeout: float = 30.0) -> Any:
        """发送请求并等待响应。"""
        if not self._connected or self._process is None or self._process.stdin is None:
            raise RuntimeError("LSP client not connected")

        msg_id = self._next_id
        self._next_id += 1

        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        msg = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
        try:
            self._process.stdin.write(encode_message(msg))
            await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as e:
            self._pending.pop(msg_id, None)
            self._connected = False
            raise RuntimeError("LSP connection lost") from e

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
        if not self._connected or self._process is None or self._process.stdin is None:
            raise RuntimeError("LSP client not connected")

        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self._process.stdin.write(encode_message(msg))
            await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            self._connected = False
            raise RuntimeError("LSP connection lost")

    def on_notification(self, method: str, handler: Any) -> None:
        """注册通知处理器。"""
        self._notification_handlers.setdefault(method, []).append(handler)

    def on_request(self, method: str, handler: Any) -> None:
        """注册服务器->客户端请求处理器。"""
        self._request_handlers[method] = handler

    async def stop(self) -> None:
        """关闭连接并终止子进程。"""
        self._connected = False
        for task in (self._reader_task, self._stderr_task):
            if task:
                task.cancel()
                try:
                    await task
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
                    break  # EOF — 进程已退出
                self._buffer += chunk
                messages, self._buffer = decode_message(self._buffer)
                for msg in messages:
                    self._dispatch(msg)
        except asyncio.CancelledError:
            pass
        finally:
            # 进程退出或读取失败 — 标记断开并清理 pending futures
            self._connected = False
            self._fail_all_pending("LSP connection lost (process exited)")

    async def _stderr_loop(self) -> None:
        """持续读取 stderr 防止管道缓冲区满导致进程挂起。"""
        assert self._process and self._process.stderr
        try:
            while True:
                chunk = await self._process.stderr.read(4096)
                if not chunk:
                    break
                # 将 stderr 输出记录到日志（调试用）
                text = chunk.decode("utf-8", errors="replace").strip()
                if text:
                    logger.debug("LSP stderr: %s", text)
        except asyncio.CancelledError:
            pass

    def _fail_all_pending(self, reason: str) -> None:
        """将所有未完成的 pending futures 设为异常。"""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(RuntimeError(reason))
        self._pending.clear()

    def _dispatch(self, msg: dict[str, Any]) -> None:
        """分发消息到对应的 future、通知处理器或请求处理器。"""
        if "id" in msg and "method" not in msg:
            # 响应消息（客户端请求的回复）
            future = self._pending.pop(msg["id"], None)
            if future and not future.done():
                future.set_result(msg)
        elif "id" in msg and "method" in msg:
            # 服务器->客户端请求（需要回复）
            handler = self._request_handlers.get(msg["method"])
            if handler:
                try:
                    result = handler(msg.get("params", {}))
                    self._send_response(msg["id"], result)
                except Exception as e:
                    self._send_error_response(msg["id"], -32603, str(e))
            else:
                # 未注册的请求方法，回复空结果
                self._send_response(msg["id"], None)
        elif "method" in msg:
            # 通知消息
            handlers = self._notification_handlers.get(msg["method"], [])
            for handler in handlers:
                try:
                    handler(msg.get("params"))
                except Exception:
                    logger.exception("Notification handler error for %s", msg["method"])

    def _send_response(self, msg_id: int, result: Any) -> None:
        """发送响应消息（回复服务器->客户端请求）。"""
        if self._process is None or self._process.stdin is None:
            return
        msg = {"jsonrpc": "2.0", "id": msg_id, "result": result}
        try:
            self._process.stdin.write(encode_message(msg))
        except (BrokenPipeError, ConnectionResetError):
            self._connected = False

    def _send_error_response(self, msg_id: int, code: int, message: str) -> None:
        """发送错误响应消息。"""
        if self._process is None or self._process.stdin is None:
            return
        msg = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
        try:
            self._process.stdin.write(encode_message(msg))
        except (BrokenPipeError, ConnectionResetError):
            self._connected = False
