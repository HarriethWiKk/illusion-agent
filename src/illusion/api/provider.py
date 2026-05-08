"""
提供商/认证能力辅助模块
======================

本模块提供 API 提供商检测和认证状态查询功能。

主要功能：
    - 检测当前活动的 API 提供商
    - 查询认证状态
    - 提供提供商元数据

类型说明：
    - ProviderInfo: 提供商元数据数据类

函数说明：
    - detect_provider: 推断活动提供商
    - auth_status: 返回认证状态字符串

使用示例：
    >>> from illusion.config.settings import load_settings
    >>> from illusion.api.provider import detect_provider, auth_status
    >>> settings = load_settings()
    >>> provider_info = detect_provider(settings)
    >>> print(f"当前提供商: {provider_info.name}")
    >>> print(f"认证状态: {auth_status(settings)}")
"""

from __future__ import annotations

from dataclasses import dataclass

from illusion.api.registry import detect_provider_from_registry
from illusion.config.settings import Settings

# 提供商认证类型映射
_AUTH_KIND: dict[str, str] = {
    "anthropic": "api_key",
    "openai_compat": "api_key",
    "openai_codex": "external_oauth",
    "anthropic_claude": "external_oauth",
}

# 语音模式支持原因映射
_VOICE_REASON: dict[str, str] = {
    "anthropic": (
        "voice mode shell exists, but live voice auth/streaming is not configured in this build"
    ),
    "openai_compat": "voice mode is not wired for OpenAI-compatible providers in this build",
    "openai_codex": "voice mode is not supported for Codex subscription auth",
    "anthropic_claude": "voice mode is not supported for Claude subscription auth",
}


@dataclass(frozen=True)
class ProviderInfo:
    """提供商元数据数据类
    
    用于 UI 和诊断的已解析提供商信息。
    
    Attributes:
        name: 提供商名称
        auth_kind: 认证类型（api_key、oauth_device、external_oauth）
        voice_supported: 是否支持语音模式
        voice_reason: 不支持语音模式的原因
    """

    name: str
    auth_kind: str
    voice_supported: bool
    voice_reason: str


def detect_provider(settings: Settings) -> ProviderInfo:
    """使用注册表推断活动提供商和大致能力集

    Args:
        settings: 应用设置对象

    Returns:
        ProviderInfo: 提供商元数据
    """
    # 从注册表检测
    spec = detect_provider_from_registry(
        model=settings.active_model_name,
        api_key=settings.api_key or None,
        base_url=settings.base_url,
    )

    if spec is not None:
        backend = spec.backend_type
        return ProviderInfo(
            name=spec.name,
            auth_kind=_AUTH_KIND.get(backend, "api_key"),
            voice_supported=False,
            voice_reason=_VOICE_REASON.get(backend, "voice mode is not supported for this provider"),
        )

    # 回退：使用 api_format 选择默认
    if settings.api_format == "openai":
        return ProviderInfo(
            name="openai-compatible",
            auth_kind="api_key",
            voice_supported=False,
            voice_reason=_VOICE_REASON["openai_compat"],
        )
    return ProviderInfo(
        name="anthropic",
        auth_kind="api_key",
        voice_supported=False,
        voice_reason=_VOICE_REASON["anthropic"],
    )


def auth_status(settings: Settings) -> str:
    """返回简洁的认证状态字符串

    Args:
        settings: 应用设置对象

    Returns:
        str: 认证状态描述
    """
    # 尝试解析认证
    try:
        resolved = settings.resolve_auth()
    except ValueError:
        return "missing"

    # 解析认证源
    if resolved.source.startswith("external:"):
        return f"configured ({resolved.source.removeprefix('external:')})"
    return "configured"
