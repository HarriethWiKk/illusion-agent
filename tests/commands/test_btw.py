""" /btw 命令处理器测试 """
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from illusion.commands.btw import btw_handler
from illusion.commands.types import CommandContext, CommandResult
from illusion.engine.query_engine import QueryEngine


def test_command_result_ephemeral_default_false():
    """CommandResult 默认 ephemeral=False。"""
    result = CommandResult(message="hello")
    assert result.ephemeral is False


def test_command_result_ephemeral_true():
    """CommandResult 可设置 ephemeral=True。"""
    result = CommandResult(message="hello", ephemeral=True)
    assert result.ephemeral is True


def _ctx():
    engine = MagicMock(spec=QueryEngine)
    ctx = CommandContext(engine=engine, cwd=".")
    return ctx, engine


@pytest.mark.asyncio
async def test_btw_empty_args_returns_usage():
    ctx, _ = _ctx()
    result = await btw_handler("", ctx)
    assert result.ephemeral is False
    assert "Usage" in (result.message or "")


@pytest.mark.asyncio
async def test_btw_returns_ephemeral_reply(monkeypatch):
    ctx, engine = _ctx()
    async def fake_run(question, eng, app_state=None):
        return "42"
    monkeypatch.setattr("illusion.commands.btw.run_side_question", fake_run)
    result = await btw_handler("what is 1+1?", ctx)
    assert result.ephemeral is True
    assert result.message == "42"


@pytest.mark.asyncio
async def test_btw_error_returns_non_ephemeral(monkeypatch):
    ctx, engine = _ctx()
    from illusion.services.side_question import SideQuestionError
    async def fake_run(question, eng, app_state=None):
        raise SideQuestionError("boom")
    monkeypatch.setattr("illusion.commands.btw.run_side_question", fake_run)
    result = await btw_handler("q", ctx)
    assert result.ephemeral is False
    assert "boom" in (result.message or "")
