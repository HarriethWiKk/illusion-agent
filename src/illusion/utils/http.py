"""HTTP 客户端工具模块
====================

提供统一的 httpx.AsyncClient 工厂函数，注入系统证书库以兼容
SteamTools（BeyondDimension）等工具注入的 HTTPS 中间人证书。

主要组件：
    - create_async_client: 统一的 httpx.AsyncClient 工厂函数
"""

from __future__ import annotations

import ssl
from typing import Any

import httpx

try:
    import truststore
    _HAS_TRUSTSTORE = True
except ImportError:
    _HAS_TRUSTSTORE = False


def _create_ssl_context() -> ssl.SSLContext:
    """创建 SSL 上下文，优先使用系统证书库（truststore）。

    truststore 会加载 Windows/macOS 系统证书库，包括 SteamTools
    注入的 MITM 证书；若 truststore 不可用，回退到 httpx 默认验证。
    """
    if _HAS_TRUSTSTORE:
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return ssl.create_default_context()


def create_async_client(**kwargs: Any) -> httpx.AsyncClient:
    """创建 httpx.AsyncClient，注入系统证书库。

    所有需要 HTTPS 的 httpx.AsyncClient 都应通过此函数创建，
    以统一处理 SSL 证书兼容性问题（如 SteamTools MITM 证书）。

    Args:
        **kwargs: 透传给 httpx.AsyncClient 的参数（timeout、follow_redirects 等）

    Returns:
        httpx.AsyncClient: 配置好系统证书库的异步客户端
    """
    ssl_context = _create_ssl_context()
    kwargs.setdefault("verify", ssl_context)
    return httpx.AsyncClient(**kwargs)
