""" /btw 命令处理器测试 """
from __future__ import annotations

from illusion.commands.types import CommandResult


def test_command_result_ephemeral_default_false():
    """CommandResult 默认 ephemeral=False。"""
    result = CommandResult(message="hello")
    assert result.ephemeral is False


def test_command_result_ephemeral_true():
    """CommandResult 可设置 ephemeral=True。"""
    result = CommandResult(message="hello", ephemeral=True)
    assert result.ephemeral is True
