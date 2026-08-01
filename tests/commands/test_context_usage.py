"""/context usage 输出格式测试（基于最后一次 API 真实用量）。"""
from unittest.mock import MagicMock, patch

import pytest

from illusion.api.usage import UsageSnapshot
from illusion.commands.session import context_handler


@pytest.mark.asyncio
async def test_context_usage_with_last_api_usage():
    """有最后一次 API 调用数据时输出真实分项。"""
    ctx = MagicMock()
    ctx.engine.messages = []
    ctx.engine.last_api_usage = UsageSnapshot(
        input_tokens=12700,
        output_tokens=12200,
        cache_read_input_tokens=175200,
        cache_creation_input_tokens=0,
    )
    ctx.engine.current_context_tokens.return_value = 200100
    ctx.engine.total_usage = UsageSnapshot(
        input_tokens=187900,
        output_tokens=12200,
        cache_read_input_tokens=1200000,
        cache_creation_input_tokens=30000,
    )
    with patch("illusion.commands.session.load_settings") as ls, \
         patch("illusion.commands.session.get_context_window", return_value=1000000):
        ls.return_value.context_window = 1000000
        result = await context_handler("usage", ctx)
    msg = result.message
    assert "上下文窗口：1,000,000 tokens" in msg
    assert "输入（命中）：175,200 tokens (18%)" in msg
    assert "输入（未命中）：12,700 tokens (1%)" in msg
    assert "输出：12,200 tokens (1%)" in msg
    assert "已用上下文：200,100 tokens (20%)" in msg
    assert "剩余：799,900 tokens" in msg
    # 累积：命中 = 1,200,000 + 30,000(写入)（不再显示累积缓存率）
    assert "累积用量：命中=1,230,000 未命中=187,900 输出=12,200" in msg
    assert "缓存率" not in msg


@pytest.mark.asyncio
async def test_context_usage_first_call_includes_cache_creation():
    """首次调用：写入缓存的量计入命中，命中率不为 0。"""
    ctx = MagicMock()
    ctx.engine.messages = []
    ctx.engine.last_api_usage = UsageSnapshot(
        input_tokens=8800,
        output_tokens=568,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=35200,
    )
    ctx.engine.current_context_tokens.return_value = 44568
    ctx.engine.total_usage = UsageSnapshot(
        input_tokens=8800,
        output_tokens=568,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=35200,
    )
    with patch("illusion.commands.session.load_settings") as ls, \
         patch("illusion.commands.session.get_context_window", return_value=1000000):
        ls.return_value.context_window = 1000000
        result = await context_handler("usage", ctx)
    msg = result.message
    # 命中 = 0(读取) + 35,200(写入) = 35,200；未命中 = 8,800
    assert "输入（命中）：35,200 tokens (4%)" in msg
    assert "输入（未命中）：8,800 tokens (1%)" in msg
    # 不再显示累积缓存率
    assert "缓存率" not in msg


@pytest.mark.asyncio
async def test_context_usage_no_last_api_usage():
    """无最后一次 API 调用数据（首次/压缩后）时输出估算汇总。"""
    ctx = MagicMock()
    ctx.engine.messages = []
    ctx.engine.last_api_usage = None
    ctx.engine.current_context_tokens.return_value = 24822
    ctx.engine.total_usage = UsageSnapshot()
    with patch("illusion.commands.session.load_settings") as ls, \
         patch("illusion.commands.session.get_context_window", return_value=1000000):
        ls.return_value.context_window = 1000000
        result = await context_handler("usage", ctx)
    msg = result.message
    assert "上下文窗口：1,000,000 tokens" in msg
    assert "已用上下文：24,822 tokens (2%)" in msg
    assert "剩余：975,178 tokens" in msg
    assert "累积用量：命中=0 未命中=0 输出=0" in msg


@pytest.mark.asyncio
async def test_context_usage_message_has_no_spark_prefix():
    """/context usage 输出的第一行不应包含 ✻ 前缀（TUI 会自动添加）。"""
    ctx = MagicMock()
    ctx.engine.messages = []
    ctx.engine.last_api_usage = UsageSnapshot(input_tokens=100, output_tokens=50)
    ctx.engine.current_context_tokens.return_value = 150
    ctx.engine.total_usage = UsageSnapshot(input_tokens=100, output_tokens=50)
    with patch("illusion.commands.session.load_settings") as ls, \
         patch("illusion.commands.session.get_context_window", return_value=1000000):
        ls.return_value.context_window = 1000000
        result = await context_handler("usage", ctx)
    first_line = result.message.split("\n")[0]
    assert not first_line.startswith("✻"), f"第一行不应包含 ✻ 前缀，实际: {first_line!r}"
    assert "上下文窗口：" in first_line
