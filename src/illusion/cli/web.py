"""Web UI 子命令"""
from __future__ import annotations

from typing import Any

import typer

from illusion.cli import web_app
from illusion.config.i18n import t as _t


@web_app.callback(invoke_without_command=True)
def web_start(
    port: int = typer.Option(3000, "--port", "-p", help="Web 服务端口"),
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
    dev: bool = typer.Option(False, "--dev", help="开发模式（启用 CORS，不 serve 静态文件）"),
    model: str | None = typer.Option(None, "--model", "-m", help="指定模型"),
    prompt: str | None = typer.Option(None, "--prompt", help="初始提示词"),
) -> None:
    """启动 Illusion Agent Web 界面 / Launch Illusion Agent Web UI"""
    import threading

    import uvicorn

    # 读取settings.json中的working_directory字段，切换工作目录
    from illusion.config import load_settings
    from illusion.ui.web.server import create_app
    from illusion.ui.web.ws_host import WebHostConfig
    settings = load_settings()
    if settings.working_directory:
        import os
        from pathlib import Path
        working_dir = Path(settings.working_directory).expanduser().resolve()
        if working_dir.exists() and working_dir.is_dir():
            os.chdir(working_dir)
        else:
            typer.echo(_t("cwd_invalid", path=settings.working_directory), err=True)

    # 渠道自动激活：有 enabled 渠道时 spawn 守护进程（与 illusion 主命令一致）
    _daemon_proc = None
    _daemon_client = None
    try:
        from illusion.channels import maybe_spawn_channel_daemon
        _daemon_proc, _daemon_client = maybe_spawn_channel_daemon()
    except (OSError, RuntimeError) as exc:
        import logging
        logging.getLogger(__name__).warning("渠道自动激活失败: %s", exc)

    # cron 自动激活（与 illusion 主命令一致）
    _cron_proc = None
    _cron_client = None
    try:
        from illusion.services.cron_spawn import maybe_spawn_cron_daemon
        _cron_proc, _cron_client = maybe_spawn_cron_daemon()
    except (OSError, RuntimeError) as exc:
        import logging
        logging.getLogger(__name__).warning("cron 自动激活失败: %s", exc)

    # PC 端渠道感知：与 illusion 主命令一致，注入 channel_hint + channel_tools
    # 让 web 端 LLM 也能看到已启用渠道并用跨渠道工具发文件
    pc_channel_hint: str | None = None
    pc_channel_tools: list[Any] | None = None
    try:
        from illusion.channels.config import load_channels_config
        from illusion.prompts.channel_hints import (
            get_channel_hint,
            list_active_sessions,
        )
        _cfg = load_channels_config()
        if _cfg.has_enabled_channels():
            other_names = _cfg.enabled_channel_names()
            _active = {
                name: list_active_sessions(name, _cfg, limit=5)
                for name in other_names
            }
            pc_channel_hint = get_channel_hint(
                current_channel=None,
                channels_config=_cfg,
                active_sessions=_active,
            )
            # 注入跨渠道工具
            from illusion.channels.tools.cross_channel import (
                ListChannelSessionsTool,
                SendToChannelTool,
            )
            pc_channel_tools = [ListChannelSessionsTool(_cfg), SendToChannelTool(_cfg)]
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        import logging
        logging.getLogger(__name__).warning("PC 渠道感知加载失败: %s", exc)

    config = WebHostConfig(
        model=model,
        channel_hint=pc_channel_hint,
        channel_tools=pc_channel_tools,
    )

    app = create_app(dev=dev, host_config=config)

    url = f"http://{host}:{port}"
    typer.echo(f"Illusion Agent Web UI: {url}")
    if not dev:
        import webbrowser
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()

    # Ctrl+C / 正常退出时关闭 IPC 连接，守护进程检测到连接归零后自动退出
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    except KeyboardInterrupt:
        pass  # IPC 连接关闭即触发守护进程退出
    finally:
        # 关闭 IPC 连接（OS 也会在进程退出时自动关闭）
        for ref in (_cron_client, _daemon_client):
            if ref is not None:
                ref.close()
