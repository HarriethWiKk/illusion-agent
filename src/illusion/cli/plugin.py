"""插件管理子命令"""
from __future__ import annotations

from pathlib import Path

import typer

from illusion.cli import plugin_app
from illusion.config.i18n import t as _t


@plugin_app.command("list")
def plugin_list() -> None:
    """列出已安装的插件"""
    from illusion.config import load_settings
    from illusion.plugins.loader import load_plugins

    settings = load_settings()
    plugins = load_plugins(settings, str(Path.cwd()))
    if not plugins:
        print(_t("plugin_none"))
        return
    for plugin in plugins:
        status = _t("plugin_enabled") if plugin.enabled else _t("plugin_disabled")
        print(f"  {plugin.name} [{status}] - {plugin.description or ''}")


@plugin_app.command("install")
def plugin_install(
    source: str = typer.Argument(..., help="Plugin source (path or URL)"),
) -> None:
    """从源路径安装插件"""
    from illusion.plugins.installer import install_plugin_from_path

    result = install_plugin_from_path(source)
    print(_t("plugin_installed", name=result))


@plugin_app.command("uninstall")
def plugin_uninstall(
    name: str = typer.Argument(..., help="Plugin name to uninstall"),
) -> None:
    """卸载插件"""
    from illusion.plugins.installer import uninstall_plugin

    uninstall_plugin(name)
    print(_t("plugin_uninstalled", name=name))
