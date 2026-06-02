"""
LSP 多语言管理器
================

管理多个 LSP 服务器实例，按文件扩展名路由请求。
按需启动服务器，管理文件同步生命周期。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from illusion.services.lsp.client import LspClient
from illusion.services.lsp.config import LspServerConfig

logger = logging.getLogger(__name__)


class LspManager:
    """管理多个 LSP 服务器实例，按文件扩展名路由。"""

    def __init__(self, configs: dict[str, LspServerConfig]) -> None:
        self._configs = configs
        self._clients: dict[str, LspClient] = {}
        self._starting: dict[str, bool] = {}

        # 构建扩展名 -> 语言 ID 映射
        self._ext_map: dict[str, str] = {}
        for lang_id, config in configs.items():
            for ext in config.extensions:
                self._ext_map[ext] = lang_id

    @property
    def supported_extensions(self) -> set[str]:
        """返回所有支持的文件扩展名。"""
        return set(self._ext_map.keys())

    def get_language_id(self, file_path: Path) -> str | None:
        """根据文件扩展名获取语言 ID。"""
        return self._ext_map.get(file_path.suffix)

    async def get_client(self, file_path: Path) -> LspClient | None:
        """获取文件对应语言的 LSP 客户端，按需启动。

        Args:
            file_path: 文件路径

        Returns:
            LspClient 实例，若该语言无配置则返回 None
        """
        lang_id = self.get_language_id(file_path)
        if lang_id is None:
            return None
        return await self._get_or_start_client(lang_id)

    async def get_client_for_language(self, lang_id: str) -> LspClient | None:
        """直接按语言 ID 获取客户端。"""
        if lang_id not in self._configs:
            return None
        return await self._get_or_start_client(lang_id)

    async def request(self, file_path: Path, method: str, params: Any, timeout: float = 30.0) -> Any:
        """向文件对应语言的 LSP 服务器发送请求。"""
        client = await self.get_client(file_path)
        if client is None:
            return None
        return await client.request(method, params, timeout=timeout)

    async def notify(self, file_path: Path, method: str, params: Any) -> None:
        """向文件对应语言的 LSP 服务器发送通知。"""
        client = await self.get_client(file_path)
        if client is not None:
            await client.notify(method, params)

    async def shutdown_all(self) -> None:
        """关闭所有 LSP 服务器。"""
        for client in self._clients.values():
            try:
                await client.stop()
            except Exception:
                logger.exception("Error stopping LSP client")
        self._clients.clear()
        self._starting.clear()

    async def initialize_client(self, lang_id: str, root_uri: str) -> None:
        """初始化指定语言的 LSP 客户端（如果尚未初始化）。"""
        client = self._clients.get(lang_id)
        if client is None or client.is_initialized:
            return
        await client.initialize(
            root_uri=root_uri,
            capabilities={
                "textDocument": {
                    "definition": {"dynamicRegistration": False},
                    "references": {"dynamicRegistration": False},
                    "hover": {"dynamicRegistration": False},
                    "documentSymbol": {"dynamicRegistration": False},
                    "implementation": {"dynamicRegistration": False},
                    "callHierarchy": {"dynamicRegistration": False},
                },
            },
        )

    async def _get_or_start_client(self, lang_id: str) -> LspClient | None:
        """获取或启动指定语言的 LSP 客户端。"""
        # 检查已有客户端是否仍可用
        if lang_id in self._clients:
            client = self._clients[lang_id]
            if client._connected:
                return client
            # 连接已断开，移除并重新启动
            logger.info("LSP client for %s disconnected, restarting", lang_id)
            self._clients.pop(lang_id, None)

        if lang_id in self._starting:
            return None  # 正在启动中

        config = self._configs.get(lang_id)
        if config is None:
            return None

        self._starting[lang_id] = True
        try:
            client = LspClient()
            await client.start(config.command, config.args)
            self._clients[lang_id] = client
            logger.info("Started LSP server for %s: %s", lang_id, config.command)
            return client
        except FileNotFoundError:
            logger.warning("LSP server not found for %s: %s", lang_id, config.command)
            return None
        except Exception:
            logger.exception("Failed to start LSP server for %s", lang_id)
            return None
        finally:
            self._starting.pop(lang_id, None)
