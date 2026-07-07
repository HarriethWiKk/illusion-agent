"""
认证相关斜杠命令
================

/login, /logout
"""

from __future__ import annotations

from illusion.commands.types import CommandContext, CommandResult
from illusion.api.auth_status import auth_status
from illusion.config.settings import load_settings, save_settings


async def login_handler(args: str, context: CommandContext) -> CommandResult:
    """显示认证状态或存储 API Key"""
    del context
    settings = load_settings()
    api_key = args.strip()
    if not api_key:
        masked = (
            f"{settings.api_key[:6]}...{settings.api_key[-4:]}"
            if settings.api_key
            else "(not configured)"
        )
        return CommandResult(
            message=(
                f"Auth status:\n"
                f"- auth_status: {auth_status(settings)}\n"
                f"- base_url: {settings.base_url or '(default)'}\n"
                f"- model: {settings.model}\n"
                f"- api_key: {masked}\n"
                "Usage: /login API_KEY"
            )
        )
    env_key = settings._active_env_key
    env = settings._active_env
    updated_env = env.model_copy(update={"api_key": api_key})
    setattr(settings, env_key, updated_env)
    save_settings(settings)
    return CommandResult(message="Stored API key in ~/.illusion/settings.json")


async def logout_handler(_: str, context: CommandContext) -> CommandResult:
    """清除已存储的 API Key"""
    del context
    settings = load_settings()
    env_key = settings._active_env_key
    env = settings._active_env
    updated_env = env.model_copy(update={"api_key": ""})
    setattr(settings, env_key, updated_env)
    save_settings(settings)
    return CommandResult(message="Cleared stored API key.")
