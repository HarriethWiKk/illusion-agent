"""
LSP 客户端
==========

参考 vscode-jsonrpc 的双向通信模式实现。
核心：独立读取循环 + 写入队列 + asyncio.Future 关联请求/响应。
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
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        path_str = unquote(parsed.path)
        if len(path_str) >= 2 and path_str[0] == "/" and path_str[2] == ":":
            path_str = path_str[1:]
        return path_str
    return unquote(uri)


def _encode(msg: dict) -> bytes:
    payload = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload


class LspClient:
    """LSP 客户端，参考 vscode-jsonrpc 的双向通信模式。"""

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._read_task: asyncio.Task | None = None
        self._write_q: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._write_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._notify_handlers: dict[str, list] = {}
        self._request_handlers: dict[str, Any] = {}
        self._buf = b""
        self._next_id = 1
        self._connected = False
        self.capabilities: dict | None = None
        self.is_initialized = False

    @property
    def is_alive(self) -> bool:
        """检查服务器进程是否仍在运行。"""
        return self._proc is not None and self._proc.returncode is None

    async def start(self, command: str, args: list[str], options: dict | None = None) -> None:
        if self._proc is not None:
            return

        kw: dict[str, Any] = {
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }
        if options and options.get("env"):
            kw["env"] = options["env"]
        if options and options.get("cwd"):
            kw["cwd"] = options["cwd"]
        if sys.platform == "win32":
            import subprocess as sp
            si = sp.STARTUPINFO()
            si.dwFlags |= sp.STARTF_USESHOWWINDOW
            si.wShowWindow = sp.SW_HIDE
            kw["startupinfo"] = si
            kw["creationflags"] = sp.CREATE_NO_WINDOW

        self._proc = await asyncio.create_subprocess_exec(command, *args, **kw)
        self._connected = True
        self._read_task = asyncio.create_task(self._reader())
        self._write_task = asyncio.create_task(self._writer())
        asyncio.create_task(self._stderr_drain())

    async def initialize(
        self, root_uri: str, capabilities: dict | None = None,
        root_path: str | None = None, process_id: int | None = None,
        initialization_options: Any = None, workspace_folders: list | None = None,
    ) -> dict:
        params: dict[str, Any] = {
            "processId": process_id or os.getpid(),
            "rootUri": root_uri,
            "capabilities": capabilities or {},
        }
        if root_path:
            params["rootPath"] = root_path
        elif root_uri.startswith("file://"):
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

        result = await self.request("initialize", params, timeout=45)
        self.capabilities = result.get("capabilities", {})
        self.is_initialized = True
        await self.notify("initialized", {})
        return result

    async def request(self, method: str, params: Any = None, timeout: float = 30, **kw) -> Any:
        if not self._connected:
            raise RuntimeError("LSP client not connected")
        if params is None:
            params = kw or {}

        msg_id = self._next_id
        self._next_id += 1
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut

        await self._write(_encode({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}))

        try:
            resp = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"LSP '{method}' timed out after {timeout}s")

        if "error" in resp:
            raise RuntimeError(f"LSP error: {resp['error'].get('message', resp['error'])}")
        return resp.get("result")

    async def notify(self, method: str, params: Any = None, **kw) -> None:
        if not self._connected:
            raise RuntimeError("LSP client not connected")
        if params is None:
            params = kw or {}
        await self._write(_encode({"jsonrpc": "2.0", "method": method, "params": params}))

    def on_notification(self, method: str, handler: Any) -> None:
        self._notify_handlers.setdefault(method, []).append(handler)

    def on_request(self, method: str, handler: Any) -> None:
        self._request_handlers[method] = handler

    async def stop(self) -> None:
        self._connected = False
        for t in (self._read_task, self._write_task):
            if t:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        if self._proc:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except Exception:
                self._proc.kill()
            self._proc = None
        self.is_initialized = False

    # --- 内部实现 ---

    async def _write(self, data: bytes) -> None:
        await self._write_q.put(data)

    async def _writer(self) -> None:
        """专用写入循环：从队列取数据，write + drain。"""
        assert self._proc and self._proc.stdin
        try:
            while True:
                data = await self._write_q.get()
                if data is None:
                    break
                try:
                    self._proc.stdin.write(data)
                    await self._proc.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    self._connected = False
                    break
        except asyncio.CancelledError:
            pass

    async def _reader(self) -> None:
        """专用读取循环：持续读取 stdout 并分发消息。"""
        assert self._proc and self._proc.stdout
        try:
            while True:
                chunk = await self._proc.stdout.read(4096)
                if not chunk:
                    break
                self._buf += chunk
                while self._buf:
                    # 解析 Content-Length 头
                    idx = self._buf.find(b"Content-Length: ")
                    if idx != 0:
                        break
                    hdr_end = self._buf.find(b"\r\n\r\n")
                    if hdr_end == -1:
                        break
                    try:
                        cl = int(self._buf[15:hdr_end])
                    except ValueError:
                        break
                    body_start = hdr_end + 4
                    if len(self._buf) < body_start + cl:
                        break
                    body = self._buf[body_start:body_start + cl]
                    self._buf = self._buf[body_start + cl:]
                    try:
                        msg = json.loads(body)
                    except json.JSONDecodeError:
                        continue
                    self._dispatch(msg)
        except asyncio.CancelledError:
            pass
        finally:
            self._connected = False
            for f in self._pending.values():
                if not f.done():
                    f.set_exception(RuntimeError("LSP connection lost"))
            self._pending.clear()

    def _dispatch(self, msg: dict) -> None:
        if "id" in msg and "method" not in msg:
            # 响应
            fut = self._pending.pop(msg["id"], None)
            if fut and not fut.done():
                fut.set_result(msg)
        elif "id" in msg and "method" in msg:
            # 服务器->客户端请求
            handler = self._request_handlers.get(msg["method"])
            if handler:
                try:
                    result = handler(msg.get("params", {}))
                except Exception as e:
                    result = None
                    logger.error("Handler error for %s: %s", msg["method"], e)
            else:
                result = None
            resp = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
            asyncio.ensure_future(self._write(_encode(resp)))
        elif "method" in msg:
            # 通知
            for h in self._notify_handlers.get(msg["method"], []):
                try:
                    h(msg.get("params"))
                except Exception:
                    logger.exception("Notification handler error for %s", msg["method"])

    async def _stderr_drain(self) -> None:
        assert self._proc and self._proc.stderr
        try:
            while True:
                line = await self._proc.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    logger.debug("LSP stderr: %s", text)
        except asyncio.CancelledError:
            pass
