"""通用斜杠命令基类测试。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from illusion.channels.base import InboundMessage
from illusion.channels.base_commands import BaseCommandHandler
from illusion.channels.feishu.session_map import FeishuSessionStore


def _msg(text: str, chat_id: str = "ou_a") -> InboundMessage:
    """构造测试入站消息。"""
    return InboundMessage(
        text=text, chat_id=chat_id, chat_type="dm",
        user_id=chat_id, user_name="tester", message_id="om_1",
    )


@pytest.fixture
def handler(tmp_path: Path):
    """用 BaseCommandHandler + FeishuSessionStore 构造测试 handler。"""
    channel = AsyncMock()
    store = FeishuSessionStore(data_dir=tmp_path)
    return BaseCommandHandler(channel=channel, session_store=store)


@pytest.mark.asyncio
async def test_help_command(handler):
    """/help 返回命令列表。"""
    result = await handler.try_handle(_msg("/help"))
    assert result is True
    handler.channel.send_text.assert_called_once()


@pytest.mark.asyncio
async def test_clear_command(handler):
    """/clear 清空会话。"""
    s = handler.session_store.get_or_create("u:ou_a", "ou_a", "dm")
    handler.session_store.save(s, [{"role": "user", "content": "old"}])
    result = await handler.try_handle(_msg("/clear"))
    assert result is True
    s2 = handler.session_store.get_or_create("u:ou_a", "ou_a", "dm")
    assert s2.messages == []


@pytest.mark.asyncio
async def test_non_command_returns_false(handler):
    """非斜杠命令返回 False。"""
    result = await handler.try_handle(_msg("你好"))
    assert result is False
    handler.channel.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_command(handler):
    """未知命令提示帮助。"""
    result = await handler.try_handle(_msg("/foobar"))
    assert result is True
    sent = handler.channel.send_text.call_args[0][1]
    assert "未知" in sent or "Unknown" in sent
