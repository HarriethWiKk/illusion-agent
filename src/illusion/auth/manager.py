"""
统一认证管理器模块
==================

本模块为 IllusionCode 提供统一的认证状态管理功能。

主要功能：
    - 管理环境（env_N）认证状态
    - 切换和配置环境
    - 存储和加载凭据（按 env_N 分组）

类说明：
    - AuthManager: 认证管理器类，负责所有认证相关的操作

使用示例：
    >>> from illusion.auth import AuthManager
    >>> manager = AuthManager()
    >>> status = manager.get_env_credential_statuses()
    >>> print(status)
"""

from __future__ import annotations

import logging
from typing import Any

from illusion.auth.storage import (
    clear_env_credentials,
    load_env_credential,
    store_env_credential,
)
from illusion.config.i18n import t as _t

log = logging.getLogger(__name__)


class AuthManager:
    """认证管理器

    通过 :mod:`illusion.auth.storage` 读写凭据，
    并通过设置跟踪当前活动的环境。
    """

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings

    @property
    def settings(self) -> Any:
        """获取设置对象（延迟加载）"""
        if self._settings is None:
            from illusion.config import load_settings
            self._settings = load_settings()
        return self._settings

    def get_active_env_key(self) -> str:
        """获取当前活动的环境键名（如 "env_1"）"""
        return self.settings._active_env_key

    def list_envs(self) -> dict[str, Any]:
        """获取所有环境配置"""
        return self.settings.list_envs()

    def get_env_credential_statuses(self) -> dict[str, Any]:
        """获取所有环境的凭据状态

        返回以 env_key 为键的字典::

            {
                "env_1": {
                    "api_format": "anthropic",
                    "base_url": "...",
                    "model": "claude-sonnet-4-6",
                    "has_credential": True,
                    "active": True,
                },
                ...
            }
        """
        active_env_key = self.get_active_env_key()
        envs = self.list_envs()
        result: dict[str, Any] = {}

        for env_key, env in envs.items():
            models = env.list_models()
            model_name = next(iter(models.values())) if models else "(无模型)"
            has_cred = bool(load_env_credential(env_key, "api_key")) or bool(env.api_key)
            result[env_key] = {
                "api_format": env.api_format,
                "base_url": env.base_url or "",
                "model": model_name,
                "has_credential": has_cred,
                "active": env_key == active_env_key,
            }

        return result

    def save_settings(self) -> None:
        """保存内存中的设置到持久化存储"""
        from illusion.config import save_settings
        save_settings(self.settings)

    def use_env(self, env_key: str) -> None:
        """切换到指定的环境

        Args:
            env_key: 环境键名（如 "env_1"）

        Raises:
            ValueError: 环境不存在
        """
        env = self.settings.get_env(env_key)
        if env is None:
            raise ValueError(_t("unknown_env", env_key=env_key))
        models = env.list_models()
        if models:
            model_key = next(iter(models.keys()))
            self.settings.model = f"{env_key}:{model_key}"
        else:
            self.settings.model = f"{env_key}:model_1"
        self._settings = self.settings
        self.save_settings()
        log.info("已切换到环境 %s", env_key)

    def update_env(
        self,
        env_key: str,
        *,
        api_format: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """更新环境配置

        Args:
            env_key: 环境键名
            api_format: API 格式
            base_url: 基础 URL
            api_key: API 密钥

        Raises:
            ValueError: 环境不存在
        """
        env = self.settings.get_env(env_key)
        if env is None:
            raise ValueError(_t("unknown_env", env_key=env_key))
        updates: dict[str, Any] = {}
        if api_format is not None:
            updates["api_format"] = api_format
        if base_url is not None:
            updates["base_url"] = base_url
        if api_key is not None:
            updates["api_key"] = api_key
        if updates:
            updated_env = env.model_copy(update=updates)
            setattr(self.settings, env_key, updated_env)
            self._settings = self.settings
            self.save_settings()

    def remove_env(self, env_key: str) -> None:
        """移除环境配置

        Args:
            env_key: 环境键名

        Raises:
            ValueError: 环境不存在或正在使用
        """
        if env_key == self.get_active_env_key():
            raise ValueError(_t("cannot_remove_active_env"))
        envs = self.settings.list_envs()
        if env_key not in envs:
            raise ValueError(_t("unknown_env", env_key=env_key))
        extras = dict(self.settings.model_extra or {})
        if env_key in extras:
            del extras[env_key]
            self._settings = self.settings.model_copy(update=extras)
            self.save_settings()

    def store_env_api_key(self, env_key: str, api_key: str) -> None:
        """存储环境的 API 密钥到 credentials.json

        Args:
            env_key: 环境键名（如 "env_1"）
            api_key: API 密钥
        """
        store_env_credential(env_key, "api_key", api_key)

    def clear_env_api_key(self, env_key: str) -> None:
        """删除环境的 API 密钥

        Args:
            env_key: 环境键名（如 "env_1"）
        """
        clear_env_credentials(env_key)

    def store_credential(self, provider: str, key: str, value: str) -> None:
        """存储凭据（兼容旧接口，按 provider 存储）

        Args:
            provider: 提供商名称
            key: 键名
            value: 凭据值
        """
        from illusion.auth.storage import store_credential
        store_credential(provider, key, value)

    def clear_credential(self, provider: str) -> None:
        """删除凭据（兼容旧接口，按 provider 清除）

        Args:
            provider: 提供商名称
        """
        from illusion.auth.storage import clear_provider_credentials
        clear_provider_credentials(provider)
