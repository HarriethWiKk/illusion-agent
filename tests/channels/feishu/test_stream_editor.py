"""流式编辑器测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from illusion.channels.feishu.stream_editor import FeishuStreamEditor


@pytest.fixture
def fake_channel():
    """构造 fake channel，记录 send_text/edit_message 调用。"""
    channel = AsyncMock()
    channel.send_text.return_value = "om_new_msg"  # 返回消息 ID
    return channel


@pytest.mark.asyncio
async def test_first_delta_creates_message(fake_channel):
    """首个 delta 立即创建消息。"""
    editor = FeishuStreamEditor(fake_channel, chat_id="oc_1", reply_to="om_orig")
    await editor.on_delta("Hello")
    fake_channel.send_text.assert_called_once_with("oc_1", "Hello", reply_to="om_orig")
    assert editor._msg_id == "om_new_msg"


@pytest.mark.asyncio
async def test_throttle_prevents_rapid_edits(fake_channel, monkeypatch):
    """节流：0.8s 内的后续 delta 不立即编辑。"""
    # 用计数器返回递增时间，避免被其他计时调用耗尽 iter
    call_count = {"n": 0}
    times_seq = [0.0, 0.5]  # 创建时 0.0，第二个 delta 0.5

    def _fake_monotonic():
        idx = min(call_count["n"], len(times_seq) - 1)
        call_count["n"] += 1
        return times_seq[idx]

    monkeypatch.setattr(
        "illusion.channels.feishu.stream_editor.time.monotonic", _fake_monotonic
    )
    editor = FeishuStreamEditor(fake_channel, chat_id="oc_1", reply_to="")
    await editor.on_delta("A")  # 创建消息，_last_edit=0.0
    await editor.on_delta("B")  # now=0.5 距上次 0.5s < 0.8，不编辑
    fake_channel.edit_message.assert_not_called()


@pytest.mark.asyncio
async def test_edit_after_interval(fake_channel, monkeypatch):
    """超过节流间隔后触发编辑。"""
    call_count = {"n": 0}
    times_seq = [0.0, 1.0]  # 创建时 0.0，第二个 delta 1.0

    def _fake_monotonic():
        idx = min(call_count["n"], len(times_seq) - 1)
        call_count["n"] += 1
        return times_seq[idx]

    monkeypatch.setattr(
        "illusion.channels.feishu.stream_editor.time.monotonic", _fake_monotonic
    )
    editor = FeishuStreamEditor(fake_channel, chat_id="oc_1", reply_to="")
    await editor.on_delta("A")  # t=0.0 创建，_last_edit=0.0
    await editor.on_delta("B")  # t=1.0 距上次 1.0s >= 0.8，编辑
    fake_channel.edit_message.assert_called_once_with("oc_1", "om_new_msg", "AB")


@pytest.mark.asyncio
async def test_finalize_edits_full_buffer(fake_channel):
    """finalize 做最后一次编辑，确保完整文本。"""
    editor = FeishuStreamEditor(fake_channel, chat_id="oc_1", reply_to="")
    await editor.on_delta("Hello")  # 创建
    await editor.on_delta(" world")  # 可能被节流
    await editor.finalize()
    # finalize 必定编辑一次完整内容
    last_call = fake_channel.edit_message.call_args
    assert last_call is not None
    assert "Hello world" in last_call[0][2]  # 第 3 个位置参数是文本


@pytest.mark.asyncio
async def test_finalize_noop_if_no_delta(fake_channel):
    """无任何 delta 时 finalize 不调用任何 API。"""
    editor = FeishuStreamEditor(fake_channel, chat_id="oc_1", reply_to="")
    await editor.finalize()
    fake_channel.send_text.assert_not_called()
    fake_channel.edit_message.assert_not_called()
