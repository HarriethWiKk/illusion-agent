"""
模型管理斜杠命令
================

/model — 显示或切换模型
"""

from __future__ import annotations

from illusion.commands.types import CommandContext, CommandResult
from illusion.config.settings import load_settings, save_settings


async def model_handler(args: str, context: CommandContext) -> CommandResult:
    """模型管理命令处理器"""
    from illusion.config.i18n import t as i18n_t
    settings = load_settings()
    tokens = args.split(maxsplit=1)
    if not tokens or tokens[0] == "show":
        env = settings._active_env
        return CommandResult(
            message=i18n_t("model_active", model=settings.model) + "\n" +
                    i18n_t("model_env_model", name=settings.active_model_name) + "\n" +
                    i18n_t("model_api_format", fmt=env.api_format) + "\n" +
                    i18n_t("model_base_url", url=env.base_url or i18n_t("model_default_url"))
        )
    if tokens[0] == "list":
        lines = []
        for env_key, env in settings.list_envs().items():
            for model_key, model_name in env.list_models().items():
                ref = f"{env_key}.{model_key}"
                active = " (active)" if ref == settings.model else ""
                lines.append(f"  {ref}{active}: {model_name} ({env.api_format})")
        return CommandResult(message=i18n_t("model_list_title") + "\n" + "\n".join(lines))
    # 切换模型
    model_ref = tokens[0] if tokens[0] != "set" else (tokens[1] if len(tokens) > 1 else "")
    if "." in model_ref:
        env_key, model_key = model_ref.split(".", 1)
        env = settings.get_env(env_key)  # type: ignore[assignment]
        if env is not None:
            model_name = env.get_model(model_key)  # type: ignore[assignment]
            if model_name:
                old_env_key = settings._active_env_key
                settings.model = model_ref
                save_settings(settings)
                context.engine.set_model(model_name)
                if context.app_state is not None:
                    context.app_state.set(model=model_name)
                needs_rebuild = env_key != old_env_key
                # 通知渠道守护进程重新加载 settings.json
                # 守护进程启动时对 settings.json 做一次性快照，切换 env 后必须刷新
                if needs_rebuild:
                    try:
                        from illusion.daemon_ipc import notify_channel_daemon_reload
                        notify_channel_daemon_reload()
                    except (ImportError, OSError, RuntimeError):
                        pass  # 守护进程未运行或通知失败，静默忽略
                return CommandResult(
                    message=i18n_t("model_set_to", ref=model_ref, name=model_name),
                    needs_api_rebuild=needs_rebuild,
                )
    return CommandResult(message=i18n_t("model_unknown", ref=model_ref))
