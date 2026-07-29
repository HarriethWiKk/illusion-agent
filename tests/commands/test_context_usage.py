"""/context usage 输出格式测试。"""
import pytest
from unittest.mock import MagicMock, patch
from illusion.commands.session import context_handler


@pytest.mark.asyncio
async def test_context_usage_measured():
    """实测后输出含 system prompt 数值。"""
    ctx = MagicMock()
    ctx.engine.messages = []
    ctx.engine.overhead_tracker.tokens = 26957
    ctx.engine.overhead_tracker.has_measured_value = True
    ctx.engine.total_usage.input_tokens = 387519
    ctx.engine.total_usage.output_tokens = 1838
    with patch("illusion.commands.session.load_settings") as ls, \
         patch("illusion.commands.session.estimate_conversation_tokens", return_value=24822), \
         patch("illusion.commands.session.get_context_window", return_value=1000000):
        ls.return_value.context_window = 1000000
        result = await context_handler("usage", ctx)
    msg = result.message
    assert "Context Window: 1,000,000 tokens" in msg
    assert "System Prompt: ~26,957 tokens (3%)" in msg
    assert "Messages: ~24,822 tokens (2%)" in msg
    assert "Estimated Used: ~51,779 tokens (5%)" in msg
    assert "Remaining: ~948,221 tokens" in msg
    assert "Cumulative API Usage: input=387,519 output=1,838" in msg
    assert "Note: System Prompt includes skills/hooks/rules/memory/channels" in msg


@pytest.mark.asyncio
async def test_context_usage_not_measured():
    """未实测时 system prompt 显示 ~ 无数字。"""
    ctx = MagicMock()
    ctx.engine.messages = []
    ctx.engine.overhead_tracker.tokens = None
    ctx.engine.overhead_tracker.has_measured_value = False
    ctx.engine.total_usage.input_tokens = 0
    ctx.engine.total_usage.output_tokens = 0
    with patch("illusion.commands.session.load_settings") as ls, \
         patch("illusion.commands.session.estimate_conversation_tokens", return_value=24822), \
         patch("illusion.commands.session.get_context_window", return_value=1000000):
        ls.return_value.context_window = 1000000
        result = await context_handler("usage", ctx)
    msg = result.message
    assert "System Prompt: ~ tokens" in msg
    assert "Messages: ~24,822 tokens (2%)" in msg
    assert "Estimated Used: ~24,822 tokens (2%)" in msg
    assert "Cumulative API Usage: input=0 output=0" in msg


@pytest.mark.asyncio
async def test_context_usage_message_has_no_spark_prefix():
    """/context usage 输出的第一行不应包含 ✻ 前缀（TUI 会自动添加）。"""
    ctx = MagicMock()
    ctx.engine.messages = []
    ctx.engine.overhead_tracker.tokens = 1000
    ctx.engine.total_usage.input_tokens = 100
    ctx.engine.total_usage.output_tokens = 50
    with patch("illusion.commands.session.load_settings") as ls, \
         patch("illusion.commands.session.estimate_conversation_tokens", return_value=24822), \
         patch("illusion.commands.session.get_context_window", return_value=1000000):
        ls.return_value.context_window = 1000000
        result = await context_handler("usage", ctx)
    first_line = result.message.split("\n")[0]
    assert not first_line.startswith("✻"), f"第一行不应包含 ✻ 前缀，实际: {first_line!r}"
    assert "Context Window:" in first_line
