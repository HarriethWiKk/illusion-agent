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
    auth_token: str = ""
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
    auth_token: str | None = None
    add_models: list[ModelEntry] | None = None
    remove_models: list[str] | None = None


class OauthPollRequest(BaseModel):
    """OAuth 轮询请求体。"""

    device_code: str = Field(..., min_length=1, description="设备码")


class UpdateUiLanguageRequest(BaseModel):
    """修改界面语言请求体。"""

    ui_language: str = Field(..., pattern="^(zh-CN|en-US)$")


class UpdateWorkingDirectoryRequest(BaseModel):
    """修改工作目录请求体。

    空字符串表示清除工作目录设置（置为 None）。
    """

    working_directory: str = ""


class UpdateMemoryRequest(BaseModel):
    """修改记忆配置请求体。

    字段均可选，只更新提供的字段：
        - enabled: 是否启用记忆功能
        - auto_extract: 是否允许后台 LLM 自动提取/整合（关闭后仅手动记录）
        - extract_model: 提取子代理模型（env_N.model_M），空串清除
        - dream_model: 整合子代理模型（env_N.model_M），空串清除
        - directory: 自定义记忆目录（绝对路径或 ~/ 开头），空串清除
    """

    enabled: bool | None = None
    auto_extract: bool | None = None
    extract_model: str | None = None
    dream_model: str | None = None
    directory: str | None = None


class UpdateThemeRequest(BaseModel):
    """修改 Web 端主题请求体。

    取值：light（浅色）/ dark（深色）/ system（跟随系统）。
    该字段仅用于 web 前端，不传递到 terminal 端。
    """

    theme: str = Field(..., pattern="^(light|dark|system)$")


def register_env_routes(app: FastAPI, host_config: Any | None = None) -> None:
    """注册 env/oauth/settings 相关 HTTP 路由到 FastAPI app。"""

    @app.get("/api/envs")
    async def list_envs() -> dict[str, Any]:
        """列出所有 env_N 配置。"""
        manager = AuthManager()
        statuses = manager.get_env_credential_statuses()
        envs = []
        for env_key, info in statuses.items():
            envs.append(
                {
                    "env_key": env_key,
                    "api_format": info.get("api_format", ""),
                    "base_url": info.get("base_url", ""),
                    "has_credential": info.get("has_credential", False),
                    "active": info.get("active", False),
                    "models": [],
                }
            )
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
        # 构建 env 配置数据（不包含敏感凭证）
        env_data: dict[str, Any] = {
            "api_format": req.api_format,
            "base_url": req.base_url or "",
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
        # 凭证保存到 credentials.json
        if req.api_key:
            manager = AuthManager()
            manager.store_env_api_key(env_key, req.api_key)
        if req.auth_token:
            manager = AuthManager()
            manager.store_env_auth_token(env_key, req.auth_token)
        return {"env_key": env_key, "success": True}

    @app.patch("/api/envs/{env_key}")
    async def update_env(env_key: str, req: UpdateEnvRequest) -> dict[str, Any]:
        """修改 env 字段。"""
        settings = load_settings()
        envs = settings.list_envs()
        if env_key not in envs:
            raise HTTPException(status_code=404, detail=_t("unknown_env", env_key=env_key))
        # 使用 AuthManager.update_env 处理 api_format/base_url/api_key/auth_token
        manager = AuthManager()
        if (
            req.api_format is not None
            or req.base_url is not None
            or req.api_key is not None
            or req.auth_token is not None
        ):
            manager.update_env(
                env_key,
                api_format=req.api_format,
                base_url=req.base_url,
                api_key=req.api_key,
                auth_token=req.auth_token,
            )
        # 处理 add_models / remove_models（直接操作 model_extra）
        if req.add_models or req.remove_models:
            settings = load_settings()  # 重新加载（update_env 可能已保存）
            # 用 model_dump → 修改 → model_validate 替代 model_copy(update=extras)，
            # 后者对 Pydantic extra 字段（env_N）更新不可靠
            data = settings.model_dump()
            env_data = data.get(env_key, {})
            if isinstance(env_data, dict):
                if req.add_models:
                    for m in req.add_models:
                        env_data[m.key] = m.value
                if req.remove_models:
                    for key in req.remove_models:
                        env_data.pop(key, None)
                data[env_key] = env_data
                new_settings = Settings.model_validate(data)
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

            auth = CodexOAuth()  # type: ignore[assignment]
            return await asyncio.to_thread(auth.start_device_flow)
        else:
            raise HTTPException(
                status_code=400, detail=_t("unknown_oauth_provider", provider=provider)
            )

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

            auth = CodexOAuth()  # type: ignore[assignment]
            try:
                success = await asyncio.to_thread(auth.poll_for_token, req.device_code)
                return {"success": success}
            except RuntimeError as e:
                return {"success": False, "error": str(e)}
        else:
            raise HTTPException(
                status_code=400, detail=_t("unknown_oauth_provider", provider=provider)
            )

    @app.patch("/api/settings/ui_language")
    async def update_ui_language(req: UpdateUiLanguageRequest) -> dict[str, Any]:
        """修改界面语言。"""
        settings = load_settings()
        new_settings = settings.model_copy(update={"ui_language": req.ui_language})
        save_settings(new_settings)
        return {"success": True}

    @app.get("/api/settings")
    async def get_settings() -> dict[str, Any]:
        """读取非敏感 settings 字段（供配置表单回显）。

        仅返回配置表单需要的字段，不含任何凭据（api_key/auth_token 存于
        credentials.json，由 /api/envs 单独管理 has_credential 标志）。
        """
        settings = load_settings()
        return {
            "ui_language": settings.ui_language,
            "working_directory": settings.working_directory,
            "model": settings.model,
            "theme": settings.theme,
            "memory": {
                "enabled": settings.memory.enabled,
                "auto_extract": settings.memory.auto_extract,
                "extract_model": settings.memory.extract_model,
                "dream_model": settings.memory.dream_model,
                "directory": settings.memory.directory,
            },
        }

    @app.patch("/api/settings/memory")
    async def update_memory(req: UpdateMemoryRequest) -> dict[str, Any]:
        """修改记忆配置。

        - enabled: 启用/禁用记忆功能
        - auto_extract: 允许/禁止后台 LLM 自动提取与整合（关闭后仅手动记录）
        - directory: 自定义记忆目录；空字符串清除（置为 None）；
          非空值经 resolve_custom_memory_dir 校验（绝对路径或 ~/ 开头），
          校验失败返回 400。
        """
        from illusion.memory.paths import resolve_custom_memory_dir

        settings = load_settings()
        updates: dict[str, Any] = {}

        if req.enabled is not None:
            updates["enabled"] = req.enabled

        if req.auto_extract is not None:
            updates["auto_extract"] = req.auto_extract

        if req.extract_model is not None:
            raw = (req.extract_model or "").strip()
            updates["extract_model"] = raw or None

        if req.dream_model is not None:
            raw = (req.dream_model or "").strip()
            updates["dream_model"] = raw or None

        if req.directory is not None:
            raw = (req.directory or "").strip()
            if not raw:
                updates["directory"] = None
            else:
                resolved = resolve_custom_memory_dir(raw)
                if resolved is None:
                    raise HTTPException(
                        status_code=400,
                        detail=_t("set_invalid_path", path=raw)
                        or "Invalid memory directory (must be an absolute path)",
                    )
                updates["directory"] = str(resolved)

        if updates:
            new_settings = settings.model_copy(
                update={"memory": settings.memory.model_copy(update=updates)}
            )
            save_settings(new_settings)
        return {"success": True, "memory": {**updates}}

    @app.patch("/api/settings/theme")
    async def update_theme(req: UpdateThemeRequest) -> dict[str, Any]:
        """修改 Web 端主题。

        取值：light / dark / system。仅写入 settings.json，不传递到 terminal 端。
        """
        settings = load_settings()
        new_settings = settings.model_copy(update={"theme": req.theme})
        save_settings(new_settings)
        return {"success": True}

    @app.patch("/api/settings/working_directory")
    async def update_working_directory(req: UpdateWorkingDirectoryRequest) -> dict[str, Any]:
        """修改工作目录。

        空字符串表示清除工作目录（置为 None）；非空字符串经
        validate_and_normalize 校验并规范化后写入 settings.json。
        校验失败返回 400。
        """
        from illusion.cli.workspace import validate_and_normalize

        raw = (req.working_directory or "").strip()
        if not raw:
            # 清除工作目录
            settings = load_settings()
            new_settings = settings.model_copy(update={"working_directory": None})
            save_settings(new_settings)
            return {"success": True, "working_directory": None}
        resolved, err = validate_and_normalize(raw)
        if resolved is None:
            raise HTTPException(status_code=400, detail=err or _t("set_invalid_path", path=raw))
        settings = load_settings()
        new_settings = settings.model_copy(update={"working_directory": str(resolved)})
        save_settings(new_settings)
        return {"success": True, "working_directory": str(resolved)}
