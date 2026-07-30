"""跨子命令共享的辅助函数"""
from __future__ import annotations

import typer

from illusion.config.i18n import MESSAGES as _I18N
from illusion.config.i18n import t as _t


def _ensure_language() -> str:
    """确保 ui_language 已设置，未设置时让用户选择

    Returns:
        str: 当前 ui_language 值
    """
    from illusion.config import load_settings, save_settings
    settings = load_settings()
    if settings.ui_language:
        return settings.ui_language

    print(_t("select_language"))
    print("  1. 中文 (zh-CN)")
    print("  2. English (en-US)")
    raw = typer.prompt("1/2", default="1")
    lang = "zh-CN" if raw.strip() == "1" else "en-US"
    settings.ui_language = lang
    save_settings(settings)
    return lang
