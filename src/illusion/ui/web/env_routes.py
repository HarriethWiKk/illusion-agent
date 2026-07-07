"""Web 端 env 配置和 OAuth 路由模块。

供 web 前端和未来 Electron 客户端通过 HTTP REST 管理 API 环境配置。
WebSocket 继续承载实时聊天流，与此处 HTTP 端点职责分离。
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from illusion.auth.manager import AuthManager
from illusion.config.i18n import t as _t
from illusion.config.settings import Settings, load_settings, save_settings


class CreateEnvRequest(BaseModel):
    """新增 env 请求体。"""
    api_format: str = Field(..., description="API 格式：anthropic/openai/copilot/codex")
    base_url: str | None = None
    api_key: str = ""
    model_1: str
    model_2: str | None = None


class ModelEntry(BaseModel):
    """模型条目。"""
    key: str = Field(..., pattern=r"^model_\d+$", description="模型键名（如 model_1）")
    value: str = Field(..., min_length=1, description="模型名称")


class UpdateEnvRequest(BaseModel):
    """修改 env 请求体。"""
    api_format: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    add_models: list[ModelEntry] | None = None
    remove_models: list[str] | None = None


class OauthPollRequest(BaseModel):
    """OAuth 轮询请求体。"""
    device_code: str = Field(..., min_length=1, description="设备码")


class UpdateUiLanguageRequest(BaseModel):
    """修改界面语言请求体。"""
    ui_language: str = Field(..., pattern="^(zh-CN|en-US)$")


def register_env_routes(app: FastAPI, host_config: Any | None = None) -> None:
    """注册 env/oauth/settings 相关 HTTP 路由到 FastAPI app。"""

    @app.get("/api/envs")
    async def list_envs() -> dict[str, Any]:
        """列出所有 env_N 配置。"""
        manager = AuthManager()
        statuses = manager.get_env_credential_statuses()
        envs = []
        for env_key, info in statuses.items():
            envs.append({
                "env_key": env_key,
                "api_format": info.get("api_format", ""),
                "base_url": info.get("base_url", ""),
                "has_credential": info.get("has_credential", False),
                "active": info.get("active", False),
                "models": [],
            })
        # 从 settings 读取 models
        settings = load_settings()
        for env in envs:
            env_config = settings.list_envs().get(env["env_key"])
            if env_config:
                env["models"] = env_config.list_models()
        active_key = manager.get_active_env_key() if envs else None
        return {"envs": envs, "active_env_key": active_key}

    @app.post("/api/envs")
    async def create_env(req: CreateEnvRequest) -> dict[str, Any]:
        """新增 env。"""
        settings = load_settings()
        # 自动分配 env_N key
        existing = set(settings.list_envs().keys())
        n = 1
        while f"env_{n}" in existing:
            n += 1
        env_key = f"env_{n}"
        # 构建 env 配置数据
        env_data: dict[str, Any] = {
            "api_format": req.api_format,
            "base_url": req.base_url or "",
            "api_key": "",
            "model_1": req.model_1,
        }
        if req.model_2:
            env_data["model_2"] = req.model_2
        # 合并到 settings 的 model_extra 中
        extras = dict(settings.model_extra or {})
        extras[env_key] = env_data
        new_settings = settings.model_copy(update=extras)
        # 如果是第一个 env，设置为 active
        if not existing:
            new_settings.model = f"{env_key}.model_1"
        # 原子写入（save_settings 内部处理 atomic_write + 字段排序）
        save_settings(new_settings)
        # 写入 api_key 到 credentials.json
        if req.api_key:
            manager = AuthManager()
            manager.store_env_api_key(env_key, req.api_key)
        return {"env_key": env_key, "success": True}

    @app.patch("/api/envs/{env_key}")
    async def update_env(env_key: str, req: UpdateEnvRequest) -> dict[str, Any]:
        """修改 env 字段。"""
        settings = load_settings()
        envs = settings.list_envs()
        if env_key not in envs:
            raise HTTPException(status_code=404, detail=_t("unknown_env", env_key=env_key))
        # 使用 AuthManager.update_env 处理 api_format/base_url/api_key
        manager = AuthManager()
        if req.api_format is not None or req.base_url is not None or req.api_key is not None:
            manager.update_env(
                env_key,
                api_format=req.api_format,
                base_url=req.base_url,
                api_key=req.api_key,
            )
        # 处理 add_models / remove_models（直接操作 model_extra）
        if req.add_models or req.remove_models:
            settings = load_settings()  # 重新加载（update_env 可能已保存）
            extras = dict(settings.model_extra or {})
            env_data = extras.get(env_key, {})
            if isinstance(env_data, dict):
                if req.add_models:
                    for m in req.add_models:
                        env_data[m.key] = m.value
                if req.remove_models:
                    for key in req.remove_models:
                        env_data.pop(key, None)
                extras[env_key] = env_data
                new_settings = settings.model_copy(update=extras)
                save_settings(new_settings)
        return {"success": True}

    @app.delete("/api/envs/{env_key}")
    async def delete_env(env_key: str) -> dict[str, Any]:
        """删除 env（拒绝删除 active env）。"""
        manager = AuthManager()
        # 先检查环境是否存在
        if env_key not in manager.list_envs():
            raise HTTPException(status_code=404, detail=_t("unknown_env", env_key=env_key))
        # 再检查是否为活动环境
        if env_key == manager.get_active_env_key():
            raise HTTPException(status_code=400, detail=_t("cannot_remove_active_env"))
        manager.remove_env(env_key)
        manager.clear_env_api_key(env_key)
        return {"success": True}

    @app.post("/api/envs/{env_key}/activate")
    async def activate_env(env_key: str) -> dict[str, Any]:
        """切换 active env。"""
        manager = AuthManager()
        try:
            manager.use_env(env_key)
        except ValueError:
            raise HTTPException(status_code=404, detail=_t("unknown_env", env_key=env_key))
        return {"success": True}

    @app.post("/api/oauth/{provider}/start")
    async def oauth_start(provider: str) -> dict[str, Any]:
        """启动 OAuth device flow。"""
        if provider == "copilot":
            from illusion.auth.copilot import CopilotAuth
            auth = CopilotAuth()
            return await asyncio.to_thread(auth.start_device_flow)
        elif provider == "codex":
            from illusion.auth.codex_oauth import CodexOAuth
            auth = CodexOAuth()
            return await asyncio.to_thread(auth.start_device_flow)
        else:
            raise HTTPException(status_code=400, detail=_t("unknown_oauth_provider", provider=provider))

    @app.post("/api/oauth/{provider}/poll")
    async def oauth_poll(provider: str, req: OauthPollRequest) -> dict[str, Any]:
        """轮询 OAuth 完成状态。"""
        if provider == "copilot":
            from illusion.auth.copilot import CopilotAuth
            auth = CopilotAuth()
            try:
                success = await asyncio.to_thread(auth.poll_for_token, req.device_code)
                return {"success": success}
            except RuntimeError as e:
                return {"success": False, "error": str(e)}
        elif provider == "codex":
            from illusion.auth.codex_oauth import CodexOAuth
            auth = CodexOAuth()
            try:
                success = await asyncio.to_thread(auth.poll_for_token, req.device_code)
                return {"success": success}
            except RuntimeError as e:
                return {"success": False, "error": str(e)}
        else:
            raise HTTPException(status_code=400, detail=_t("unknown_oauth_provider", provider=provider))

    @app.patch("/api/settings/ui_language")
    async def update_ui_language(req: UpdateUiLanguageRequest) -> dict[str, Any]:
        """修改界面语言。"""
        settings = load_settings()
        new_settings = settings.model_copy(update={"ui_language": req.ui_language})
        save_settings(new_settings)
        return {"success": True}
