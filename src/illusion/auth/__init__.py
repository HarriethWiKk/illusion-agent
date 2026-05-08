"""
认证模块
========

本模块提供 IllusionCode 统一的认证管理功能。

主要组件：
    - AuthManager: 认证管理器
    - ApiKeyFlow: API 密钥认证流程
    - store_credential/load_credential: 凭据存储/加载（按 provider）
    - store_env_credential/load_env_credential: 凭据存储/加载（按 env_N）
    - store_external_binding/load_external_binding: 外部绑定存储/加载
    - encrypt/decrypt: 加密/解密功能

使用示例：
    >>> from illusion.auth import AuthManager, ApiKeyFlow
    >>> manager = AuthManager()
    >>> flow = ApiKeyFlow(prompt_text="输入 API 密钥")
    >>> key = flow.run()
"""

from illusion.auth.flows import ApiKeyFlow
from illusion.auth.manager import AuthManager
from illusion.auth.storage import (
    clear_env_credentials,
    clear_provider_credentials,
    decrypt,
    encrypt,
    load_credential,
    load_env_credential,
    load_external_binding,
    store_credential,
    store_env_credential,
    store_external_binding,
)

__all__ = [
    "AuthManager",
    "ApiKeyFlow",
    "store_credential",
    "load_credential",
    "store_env_credential",
    "load_env_credential",
    "clear_env_credentials",
    "store_external_binding",
    "load_external_binding",
    "clear_provider_credentials",
    "encrypt",
    "decrypt",
]
