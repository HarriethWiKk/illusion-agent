"""
统一认证管理器模块
==================

本模块为 IllusionCode 提供统一的认证状态管理功能。

主要功能：
    - 管理提供商认证状态
    - 切换和配置环境（env_N）
    - 存储和加载凭据
    - 获取认证源配置状态

类说明：
    - AuthManager: 认证管理器类，负责所有认证相关的操作

使用示例：
    >>> from illusion.auth import AuthManager
    >>> manager = AuthManager()
    >>> status = manager.get_auth_status()
    >>> print(status)
"""

from __future__ import annotations

import logging
from typing import Any

from illusion.auth.storage import (
    clear_provider_credentials,
    load_credential,
    store_credential,
)

# 模块级日志记录器
log = logging.getLogger(__name__)

# Illusion 已知的提供商列表
_KNOWN_PROVIDERS = [
    "anthropic",
    "openai",
    "copilot",
]


class AuthManager:
    """认证管理器

    提供商认证状态的中央管理类。
    通过 :mod:`illusion.auth.storage` 读写凭据，
    并通过设置跟踪当前活动的环境。

    Attributes:
        _settings: 设置对象（延迟加载）

    使用示例：
        >>> manager = AuthManager()
        >>> provider = manager.get_active_provider()
        >>> print(f"当前提供商: {provider}")
    """

    def __init__(self, settings: Any | None = None) -> None:
        # 延迟加载设置，以便管理器可以在不导入完整配置子系统的情况下实例化
        self._settings = settings

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    @property
    def settings(self) -> Any:
        """获取设置对象（延迟加载）"""
        if self._settings is None:
            from illusion.config import load_settings

            self._settings = load_settings()
        return self._settings

    def _provider_from_settings(self) -> str:
        """从设置中获取当前的提供商名称

        Returns:
            str: 提供商名称
        """
        return self.settings.provider

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def get_active_provider(self) -> str:
        """获取当前活动的提供商名称

        Returns:
            str: 提供商名称
        """
        return self._provider_from_settings()

    def get_active_env_key(self) -> str:
        """获取当前活动的环境键名

        Returns:
            str: 环境键名（如 "env_1"）
        """
        return self.settings._active_env_key

    def list_envs(self) -> dict[str, Any]:
        """获取所有环境配置

        Returns:
            dict[str, EnvConfig]: 环境配置字典
        """
        return self.settings.list_envs()

    def get_auth_status(self) -> dict[str, Any]:
        """获取所有已知提供商的认证状态

        返回以提供商名称为键的字典，结构如下::

            {
                "anthropic": {
                    "configured": True,
                    "source": "env",   # "env", "file", 或 "missing"
                    "active": True,
                },
                ...
            }

        Returns:
            dict[str, Any]: 提供商认证状态字典
        """
        import os

        active = self.get_active_provider()
        result: dict[str, Any] = {}

        for provider in _KNOWN_PROVIDERS:
            configured = False
            source = "missing"

            if provider == "anthropic":
                if os.environ.get("ANTHROPIC_API_KEY"):
                    configured = True
                    source = "env"
                elif load_credential("anthropic", "api_key"):
                    configured = True
                    source = "file"
                elif self.settings.api_key and self.settings.provider == "anthropic":
                    configured = True
                    source = "config"

            elif provider == "openai":
                if os.environ.get("OPENAI_API_KEY"):
                    configured = True
                    source = "env"
                elif load_credential("openai", "api_key"):
                    configured = True
                    source = "file"
                elif self.settings.api_key and self.settings.provider == "openai":
                    configured = True
                    source = "config"

            elif provider == "copilot":
                from illusion.api.copilot_auth import load_copilot_auth

                if load_copilot_auth():
                    configured = True
                    source = "file"

            result[provider] = {
                "configured": configured,
                "source": source,
                "active": provider == active,
            }

        return result

    def get_env_statuses(self) -> dict[str, Any]:
        """获取所有环境配置的状态

        Returns:
            dict[str, Any]: 环境状态字典
        """
        active_env_key = self.get_active_env_key()
        envs = self.list_envs()
        result: dict[str, Any] = {}

        for env_key, env in envs.items():
            models = env.list_models()
            model_name = next(iter(models.values())) if models else "(no models)"
            result[env_key] = {
                "api_format": env.api_format,
                "base_url": env.base_url,
                "model": model_name,
                "has_api_key": bool(env.api_key),
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
            raise ValueError(f"Unknown env: {env_key!r}")
        # 切换到该环境的第一个模型
        models = env.list_models()
        if models:
            model_key = next(iter(models.keys()))
            self.settings.model = f"{env_key}:{model_key}"
        else:
            self.settings.model = f"{env_key}:model_1"
        self._settings = self.settings
        self.save_settings()
        log.info("Switched active env to %s", env_key)

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
            raise ValueError(f"Unknown env: {env_key!r}")
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
            raise ValueError("Cannot remove the active env.")
        envs = self.settings.list_envs()
        if env_key not in envs:
            raise ValueError(f"Unknown env: {env_key!r}")
        # 从 extras 中移除
        extras = dict(self.settings.model_extra or {})
        if env_key in extras:
            del extras[env_key]
            self._settings = self.settings.model_copy(update=extras)
            self.save_settings()

    def store_credential(self, provider: str, key: str, value: str) -> None:
        """存储给定提供商的凭据

        Args:
            provider: 提供商名称
            key: 键名
            value: 凭据值
        """
        store_credential(provider, key, value)
        # 如果存储的是当前活跃环境的 api_key，同步到设置
        if key == "api_key" and provider == self.settings.provider:
            try:
                env = self.settings._active_env
                env.api_key = value
                setattr(self.settings, self.settings._active_env_key, env)
                self._settings = self.settings
                self.save_settings()
            except Exception as exc:
                log.warning("Could not sync api_key to settings: %s", exc)

    def clear_credential(self, provider: str) -> None:
        """删除给定提供商的所有存储凭据

        Args:
            provider: 提供商名称
        """
        clear_provider_credentials(provider)
        # 如果这是活动提供商，也清除设置中的 api_key
        if provider == self.settings.provider:
            try:
                env = self.settings._active_env
                env.api_key = ""
                setattr(self.settings, self.settings._active_env_key, env)
                self._settings = self.settings
                self.save_settings()
            except Exception as exc:
                log.warning("Could not clear api_key from settings: %s", exc)
