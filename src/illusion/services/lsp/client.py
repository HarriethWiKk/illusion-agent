"""
LSP 客户端
==========

基于 pylspclient 的 LSP 客户端实现。
pylspclient 正确处理 JSON-RPC 协议（消息分帧、flush、双向通信），
等价于参考项目使用的 vscode-jsonrpc。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import pylspclient

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


class LspClient:
    """基于 pylspclient 的 LSP 客户端。

    pylspclient 使用 JsonRpcEndpoint 正确处理 JSON-RPC 协议：
    - send_request: 添加 Content-Length 头 + write + flush
    - recv_response: 读取 Content-Length 头 + 读取 body + JSON 解析
    - LspEndpoint: 专用线程持续读取消息并分发
    """

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._endpoint: pylspclient.LspEndpoint | None = None
        self._lsp_client: pylspclient.LspClient | None = None
        self._notification_handlers: dict[str, list] = {}
        self._request_handlers: dict[str, Any] = {}
        self._connected: bool = False
        self.capabilities: dict[str, Any] | None = None
        self.is_initialized: bool = False

    async def start(self, command: str, args: list[str], options: dict[str, Any] | None = None) -> None:
        """启动 LSP 服务器子进程。"""
        if self._process is not None:
            return  # 已启动，静默返回
        if self._endpoint is not None:
            return  # 已启动，静默返回

        kwargs: dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
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

        self._process = subprocess.Popen([command] + args, **kwargs)
        self._connected = True

        # 创建 pylspclient 的 JSON-RPC 端点和 LSP 端点
        json_rpc_endpoint = pylspclient.JsonRpcEndpoint(self._process.stdin, self._process.stdout)

        # 注册请求处理器（服务器->客户端）
        method_callbacks = {
            "workspace/configuration": self._handle_workspace_config,
            "window/workDoneProgress/create": lambda params: None,
        }

        self._endpoint = pylspclient.LspEndpoint(
            json_rpc_endpoint,
            method_callbacks=method_callbacks,
            notify_callbacks=self._notification_handlers,
            timeout=60,
        )
        self._endpoint.daemon = True
        self._endpoint.start()

        # 创建 LSP 客户端
        self._lsp_client = pylspclient.LspClient(self._endpoint)

        # stderr 日志
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()

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
        if not self._lsp_client:
            raise RuntimeError("LSP client not started")

        if root_path is None and root_uri.startswith("file://"):
            root_path = _uri_to_path(root_uri)

        if workspace_folders is None:
            workspace_folders = [{
                "uri": root_uri,
                "name": Path(root_path or "").name or "workspace",
            }]

        # pylspclient 的 initialize 方法在单独线程中运行
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._lsp_client.initialize(
                processId=process_id or os.getpid(),
                rootPath=root_path or "",
                rootUri=root_uri,
                initializationOptions=initialization_options or {},
                capabilities=capabilities or {},
                trace="off",
                workspaceFolders=workspace_folders,
            ),
        )

        self.capabilities = dict(result.get("capabilities", {})) if result else {}
        self.is_initialized = True

        # 发送 initialized 通知
        await loop.run_in_executor(None, self._lsp_client.initialized)

        return dict(result) if result else {}

    async def request(self, method: str, params: Any = None, timeout: float = 30.0, **kwargs: Any) -> Any:
        """发送请求并等待响应。params 为 dict 或通过 kwargs 传递。"""
        if not self._connected or not self._endpoint:
            raise RuntimeError("LSP client not connected")

        if params is None:
            params = kwargs
        elif kwargs:
            params = {**params, **kwargs}

        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self._endpoint.call_method(method, **params)),
                timeout=timeout,
            )
            return result
        except pylspclient.lsp_errors.ResponseError as e:
            raise RuntimeError(f"LSP error: {e}")

    async def notify(self, method: str, params: Any = None, **kwargs: Any) -> None:
        """发送通知。params 为 dict 或通过 kwargs 传递。"""
        if not self._connected or not self._endpoint:
            raise RuntimeError("LSP client not connected")

        if params is None:
            params = kwargs
        elif kwargs:
            params = {**params, **kwargs}

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._endpoint.send_notification(method, **params))

    def on_notification(self, method: str, handler: Any) -> None:
        """注册通知处理器。"""
        self._notification_handlers[method] = handler
        # pylspclient 的 notify_callbacks 在 LspEndpoint.run() 中使用
        # 如果 endpoint 已启动，需要动态更新
        if self._endpoint:
            self._endpoint.notify_callbacks[method] = handler

    def on_request(self, method: str, handler: Any) -> None:
        """注册服务器->客户端请求处理器。"""
        self._request_handlers[method] = handler
        if self._endpoint:
            self._endpoint.method_callbacks[method] = handler

    async def stop(self) -> None:
        """关闭连接并终止子进程。"""
        self._connected = False
        if self._endpoint:
            self._endpoint.stop()
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                self._process.kill()
            self._process = None
        self.is_initialized = False

    def _handle_workspace_config(self, params: Any) -> list:
        """处理 workspace/configuration 请求。"""
        items = params.get("items", []) if isinstance(params, dict) else []
        return [{}] * len(items)

    def _read_stderr(self) -> None:
        """读取 stderr 输出。"""
        if not self._process or not self._process.stderr:
            return
        try:
            while True:
                line = self._process.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    logger.debug("LSP stderr: %s", text)
        except Exception:
            pass
