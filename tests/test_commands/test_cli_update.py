"""CLI update 子命令的文件占用检测测试。"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_update_returns_locked_hint_on_permission_denied():
    """pip 输出包含 'Access is denied' 时返回文件占用提示。"""
    from illusion.commands.types import CommandResult
    from illusion.config.i18n import t

    with patch("illusion.commands.misc._check_pypi_latest", return_value=None), \
         patch("illusion.commands.misc._run_pip_upgrade", return_value=(False, "ERROR: Access is denied for 'illusion-agent'")):
        from illusion.cli.update import _update_cli
        result = await _update_cli("")
    assert isinstance(result, CommandResult)
    assert result.message == t("update_locked_by_running_process")


@pytest.mark.asyncio
async def test_update_returns_locked_hint_on_being_used():
    """pip 输出包含 'being used by another process' 时返回文件占用提示。"""
    from illusion.commands.types import CommandResult
    from illusion.config.i18n import t

    with patch("illusion.commands.misc._check_pypi_latest", return_value=None), \
         patch("illusion.commands.misc._run_pip_upgrade", return_value=(False, "WinError 32: being used by another process")):
        from illusion.cli.update import _update_cli
        result = await _update_cli("")
    assert isinstance(result, CommandResult)
    assert result.message == t("update_locked_by_running_process")


@pytest.mark.asyncio
async def test_update_returns_generic_failed_on_other_error():
    """其他 pip 错误返回通用 update_failed。"""
    from illusion.commands.types import CommandResult
    from illusion.config.i18n import t

    with patch("illusion.commands.misc._check_pypi_latest", return_value=None), \
         patch("illusion.commands.misc._run_pip_upgrade", return_value=(False, "some other error")):
        from illusion.cli.update import _update_cli
        result = await _update_cli("")
    assert isinstance(result, CommandResult)
    assert result.message == t("update_failed", error="some other error")
