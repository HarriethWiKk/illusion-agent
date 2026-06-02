"""
LSP 客户端
==========

轻量级 JSON-RPC 2.0 over stdio 客户端，用于与外部 LSP 服务器通信。
参考 vscode-jsonrpc 的双向通信模式实现。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)


def _uri_to_path(uri: str) -> str:
    """将 file:// URI 转换为本地路径字符串。"""
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        path_str = unquote(parsed.path)
        if len(path_str) >= 2 and path_str[0] == "/" and path_str[2] == ":":
            path_str = path_str[1:]
        return path_str
    return unquote(uri)


def _encode_message(body: dict[str, Any]) -> bytes:
    """将 JSON-RPC 消息编码为 LSP 带 Content-Length 头的字节序列。"""
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
    return header + payload


def _decode_messages(data: bytes) -> tuple[list[dict[str, Any]], bytes]:
    """从字节流中解码 JSON-RPC 消息。"""
    messages: list[dict[str, Any]] = []
    while data:
        idx = data.find(b"Content-Length: ")
        if idx != 0:
            break
        header_end = data.find(b"\r\n\r\n")
        if header_end == -1:
            break
        try:
            content_length = int(data[15:header_end].strip())
        except ValueError:
            break
        body_start = header_end + 4
        if len(data) < body_start + content_length:
            break
        try:
            messages.append(json.loads(data[body_start:body_start + content_length]))
        except json.JSONDecodeError:
            pass
        data = data[body_start + content_length:]
    return messages, data


class LspClient:
    """单个 LSP 服务器的客户端连接。

    参考 vscode-jsonrpc 的双向通信模式：
    - 独立的读取循环持续处理入站消息
    - 写入队列确保消息按序发送并正确刷新
    - 请求/响应通过 ID 关联
    - 服务器->客户端请求通过注册的处理器响应
    """

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._read_task: asyncio.Task | None = None
        self._write_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._write_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._notification_handlers: dict[str, list] = {}
        self._request_handlers: dict[str, Any] = {}
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
        if options and options.get("cwd"):
            kwargs["cwd"] = options["cwd"]

        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        self._process = await asyncio.create_subprocess_exec(command, *args, **kwargs)
        self._connected = True
        self._read_task = asyncio.create_task(self._read_loop())
        self._write_task = asyncio.create_task(self._write_loop())

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
        params: dict[str, Any] = {
            "processId": process_id or os.getpid(),
            "rootUri": root_uri,
            "capabilities": capabilities or {},
        }
        if root_path:
            params["rootPath"] = root_path
        else:
            if root_uri.startswith("file://"):
                params["rootPath"] = _uri_to_path(root_uri)

        if initialization_options is not None:
            params["initializationOptions"] = initialization_options

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
        if not self._connected:
            raise RuntimeError("LSP client not connected")

        msg_id = self._next_id
        self._next_id += 1

        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        msg = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
        await self._enqueue_write(_encode_message(msg))

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
        if not self._connected:
            raise RuntimeError("LSP client not connected")
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        await self._enqueue_write(_encode_message(msg))

    def on_notification(self, method: str, handler: Any) -> None:
        """注册通知处理器。"""
        self._notification_handlers.setdefault(method, []).append(handler)

    def on_request(self, method: str, handler: Any) -> None:
        """注册服务器->客户端请求处理器。"""
        self._request_handlers[method] = handler

    async def stop(self) -> None:
        """关闭连接并终止子进程。"""
        self._connected = False
        for task in (self._read_task, self._write_task):
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

    async def _enqueue_write(self, data: bytes) -> None:
        """将数据加入写入队列。"""
        await self._write_queue.put(data)

    async def _write_loop(self) -> None:
        """持续从队列取出数据并写入 stdin。"""
        assert self._process and self._process.stdin
        try:
            while True:
                data = await self._write_queue.get()
                if data is None:
                    break
                try:
                    self._process.stdin.write(data)
                    await self._process.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    self._connected = False
                    break
        except asyncio.CancelledError:
            pass

    async def _read_loop(self) -> None:
        """持续读取 stdout 并分发消息。"""
        assert self._process and self._process.stdout
        try:
            while True:
                chunk = await self._process.stdout.read(4096)
                if not chunk:
                    break
                self._buffer += chunk
                messages, self._buffer = _decode_messages(self._buffer)
                for msg in messages:
                    self._dispatch(msg)
        except asyncio.CancelledError:
            pass
        finally:
            self._connected = False
            self._fail_all_pending("LSP connection lost (process exited)")

    def _dispatch(self, msg: dict[str, Any]) -> None:
        """分发消息。"""
        if "id" in msg and "method" not in msg:
            # 响应消息
            future = self._pending.pop(msg["id"], None)
            if future and not future.done():
                future.set_result(msg)
        elif "id" in msg and "method" in msg:
            # 服务器->客户端请求
            handler = self._request_handlers.get(msg["method"])
            if handler:
                try:
                    result = handler(msg.get("params", {}))
                    self._send_response_now(msg["id"], result)
                except Exception as e:
                    self._send_error_now(msg["id"], -32603, str(e))
            else:
                self._send_response_now(msg["id"], None)
        elif "method" in msg:
            # 通知
            handlers = self._notification_handlers.get(msg["method"], [])
            for handler in handlers:
                try:
                    handler(msg.get("params"))
                except Exception:
                    logger.exception("Notification handler error for %s", msg["method"])

    def _send_response_now(self, msg_id: int, result: Any) -> None:
        """同步写入响应到写入队列。"""
        msg = {"jsonrpc": "2.0", "id": msg_id, "result": result}
        asyncio.ensure_future(self._enqueue_write(_encode_message(msg)))

    def _send_error_now(self, msg_id: int, code: int, message: str) -> None:
        """同步写入错误响应到写入队列。"""
        msg = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
        asyncio.ensure_future(self._enqueue_write(_encode_message(msg)))

    def _fail_all_pending(self, reason: str) -> None:
        """将所有未完成的 pending futures 设为异常。"""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(RuntimeError(reason))
        self._pending.clear()
