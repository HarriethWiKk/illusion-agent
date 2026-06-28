"""QQ C2C 流式消息控制器单元测试

覆盖：
- send_c2c_stream_message API 封装（请求体构造、stream_msg_id 复用、响应解析）
- QQStreamingController 状态机（idle → streaming → completed/aborted）
- 首次启动流程（stream_msg_id 获取）
- 节流 flush（500ms 间隔、长间隔批量、去重）
- 终态收尾（input_state=DONE 分片）
- 降级策略（should_fallback_to_static）
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from illusion.channels.qq.api import (
    STREAM_INPUT_MODE_REPLACE,
    STREAM_INPUT_STATE_DONE,
    STREAM_INPUT_STATE_GENERATING,
    send_c2c_stream_message,
)
from illusion.channels.qq.streaming import QQStreamingController


# ─── 辅助函数 ──────────────────────────────────────────────


def _mock_response(data: dict | None = None) -> MagicMock:
    """构造模拟 aiohttp 响应"""
    resp = MagicMock()
    resp.status = 200
    if data is None:
        resp.text = AsyncMock(return_value="")
        resp.json = AsyncMock(return_value={})
    else:
        import json
        resp.text = AsyncMock(return_value=json.dumps(data))
        resp.json = AsyncMock(return_value=data)
    return resp


def _mock_session(response_data: dict | None = None) -> MagicMock:
    """构造模拟 aiohttp.ClientSession"""
    session = MagicMock()
    # QQ stream_messages API 响应字段名是 id（不是 stream_msg_id）
    # 参照 openclaw-main types.ts:60 MessageResponse.id
    resp = _mock_response(response_data or {"id": "smid_123"})
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=None)
    session.post = MagicMock(return_value=ctx)
    return session


# ─── API 封装测试 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_c2c_stream_message_first_chunk() -> None:
    """首次分片：不传 stream_msg_id，请求体含 event_id（必填）"""
    session = _mock_session({"id": "smid_123"})
    resp = await send_c2c_stream_message(
        session, "token_abc", "openid_xyz",
        content="Hello",
        input_state=STREAM_INPUT_STATE_GENERATING,
        msg_id="msg_in_001",
        msg_seq=42,
        index=1,
    )
    # QQ API 响应字段是 id（不是 stream_msg_id）
    assert resp["id"] == "smid_123"
    # 验证请求 URL 和 body
    session.post.assert_called_once()
    call_args = session.post.call_args
    url = call_args[0][0]
    assert "/v2/users/openid_xyz/stream_messages" in url
    body = call_args[1]["json"]
    assert body["input_mode"] == STREAM_INPUT_MODE_REPLACE
    assert body["input_state"] == STREAM_INPUT_STATE_GENERATING
    assert body["content_raw"] == "Hello"
    assert body["msg_id"] == "msg_in_001"
    assert body["msg_seq"] == 42
    assert body["index"] == 1
    assert body["event_id"] == "msg_in_001"  # event_id 默认复用 msg_id
    assert "stream_msg_id" not in body  # 首次不传


@pytest.mark.asyncio
async def test_send_c2c_stream_message_subsequent_chunk() -> None:
    """后续分片：传 stream_msg_id，请求体包含该字段"""
    session = _mock_session({})
    await send_c2c_stream_message(
        session, "token_abc", "openid_xyz",
        content="Hello world",
        input_state=STREAM_INPUT_STATE_GENERATING,
        msg_id="msg_in_001",
        msg_seq=42,
        index=2,
        stream_msg_id="smid_123",
    )
    body = session.post.call_args[1]["json"]
    assert body["stream_msg_id"] == "smid_123"


@pytest.mark.asyncio
async def test_send_c2c_stream_message_done_state() -> None:
    """终结分片：input_state=DONE"""
    session = _mock_session({})
    await send_c2c_stream_message(
        session, "token_abc", "openid_xyz",
        content="Final text",
        input_state=STREAM_INPUT_STATE_DONE,
        msg_id="msg_in_001",
        msg_seq=42,
        index=5,
        stream_msg_id="smid_123",
    )
    body = session.post.call_args[1]["json"]
    assert body["input_state"] == STREAM_INPUT_STATE_DONE


@pytest.mark.asyncio
async def test_send_c2c_stream_message_content_truncation() -> None:
    """内容超长时被截断到 MAX_MESSAGE_LENGTH"""
    from illusion.channels.qq.api import MAX_MESSAGE_LENGTH
    session = _mock_session({})
    long_content = "x" * (MAX_MESSAGE_LENGTH + 100)
    await send_c2c_stream_message(
        session, "token_abc", "openid_xyz",
        content=long_content,
        input_state=STREAM_INPUT_STATE_GENERATING,
        msg_id="msg_001",
        msg_seq=1,
        index=1,
    )
    body = session.post.call_args[1]["json"]
    assert len(body["content_raw"]) == MAX_MESSAGE_LENGTH


# ─── Controller 状态机测试 ─────────────────────────────────


@pytest.mark.asyncio
async def test_controller_initial_state() -> None:
    """初始状态：phase=idle，无 stream_msg_id"""
    session = _mock_session()
    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )
    assert controller.phase == "idle"
    assert controller.stream_msg_id == ""
    assert controller.should_fallback_to_static is False
    assert controller.accumulated_text == ""


@pytest.mark.asyncio
async def test_controller_starts_on_first_text() -> None:
    """首个非空白文本触发流式启动：从响应 id 字段获取 stream_msg_id，首帧 index=0"""
    session = _mock_session({"id": "smid_abc"})
    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )
    await controller.on_text("Hello")
    assert controller.phase == "streaming"
    assert controller.stream_msg_id == "smid_abc"
    # 首次启动应发送一个分片
    assert session.post.call_count == 1
    # 首帧 index 必须为 0（参考 openclaw-main streaming-c2c.ts:1034 后递增）
    # QQ 协议要求 index 从 0 开始，否则客户端显示"该消息类型暂不支持查看"
    body = session.post.call_args[1]["json"]
    assert body["index"] == 0


@pytest.mark.asyncio
async def test_controller_start_aborts_when_response_missing_id() -> None:
    """响应缺少 id 字段 → 抛异常 → aborted → should_fallback_to_static=True

    参照 openclaw-main streaming-c2c.ts:1007: if (!resp.id) throw
    """
    # 响应成功但无 id 字段（API 版本不兼容或异常情况）
    session = _mock_session({"code": 0, "message": "ok"})
    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )
    await controller.on_text("Hello")
    assert controller.phase == "aborted"
    assert controller.should_fallback_to_static is True
    assert controller.stream_msg_id == ""


@pytest.mark.asyncio
async def test_controller_ignores_empty_text() -> None:
    """空文本不触发启动"""
    session = _mock_session()
    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )
    await controller.on_text("")
    await controller.on_text("   ")  # 仅空白
    assert controller.phase == "idle"
    assert session.post.call_count == 0


@pytest.mark.asyncio
async def test_controller_start_failure_aborts() -> None:
    """首次分片发送失败 → aborted 状态 → should_fallback_to_static=True"""
    session = MagicMock()
    ctx = AsyncMock()
    resp = MagicMock()
    resp.status = 500
    resp.text = AsyncMock(return_value="server error")
    resp.raise_for_status = MagicMock(side_effect=RuntimeError("HTTP 500"))
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=None)
    session.post = MagicMock(return_value=ctx)

    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )
    await controller.on_text("Hello")
    assert controller.phase == "aborted"
    assert controller.should_fallback_to_static is True


@pytest.mark.asyncio
async def test_controller_throttle_batches_rapid_chunks() -> None:
    """节流：500ms 内的多个 chunk 只触发首次启动 + 少量 patch"""
    session = _mock_session({"id": "smid_abc"})
    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )
    # 首个 chunk 立即启动
    await controller.on_text("chunk0")
    assert session.post.call_count == 1
    # 500ms 内的后续 chunk 应被节流（进延迟队列）
    for i in range(1, 5):
        await controller.on_text(f"chunk{i}")
    # 等待延迟 flush 执行
    await asyncio.sleep(0.6)
    # 应只触发少量 patch（节流合并）
    assert 2 <= session.post.call_count <= 3


@pytest.mark.asyncio
async def test_controller_throttle_dedup_skips_unchanged_text() -> None:
    """去重：相同文本不触发重复 API 调用"""
    session = _mock_session({"id": "smid_abc"})
    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )
    await controller.on_text("Hello")
    first_count = session.post.call_count
    assert first_count == 1
    # 强制 flush 相同文本：应被去重跳过
    controller._last_flush_time = 0.0  # 重置时间戳强制进入 flush
    await controller._flush()
    assert session.post.call_count == first_count  # 无新增调用


@pytest.mark.asyncio
async def test_controller_complete_sends_done_chunk() -> None:
    """complete() 发送 input_state=DONE 的终结分片"""
    session = _mock_session({"id": "smid_abc"})
    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )
    await controller.on_text("Hello")
    await asyncio.sleep(0.6)  # 等待节流完成
    count_before_complete = session.post.call_count
    await controller.complete()
    assert controller.phase == "completed"
    # 应多发一个 DONE 分片
    assert session.post.call_count == count_before_complete + 1
    # 验证最后一个调用的 input_state=DONE
    last_body = session.post.call_args[1]["json"]
    assert last_body["input_state"] == STREAM_INPUT_STATE_DONE


@pytest.mark.asyncio
async def test_controller_complete_without_any_chunk_falls_back() -> None:
    """complete() 时从未发过分片 → should_fallback_to_static=True"""
    session = _mock_session()
    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )
    # 不调用 on_text，直接 complete
    await controller.complete()
    assert controller.phase == "completed"
    assert controller.should_fallback_to_static is True
    # 不应发送任何 DONE 分片
    assert session.post.call_count == 0


@pytest.mark.asyncio
async def test_controller_abort_does_not_send_done() -> None:
    """abort() 不发 DONE 分片，直接进入 aborted 状态"""
    session = _mock_session({"id": "smid_abc"})
    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )
    await controller.on_text("Hello")
    await asyncio.sleep(0.6)
    count_before_abort = session.post.call_count
    await controller.abort("user cancelled")
    assert controller.phase == "aborted"
    # abort 不应触发新的 API 调用
    assert session.post.call_count == count_before_abort


@pytest.mark.asyncio
async def test_controller_fallback_after_abort() -> None:
    """abort 后 should_fallback_to_static=True（从未成功发出分片时）"""
    session = MagicMock()
    ctx = AsyncMock()
    resp = MagicMock()
    resp.status = 500
    resp.text = AsyncMock(return_value="error")
    resp.raise_for_status = MagicMock(side_effect=RuntimeError("HTTP 500"))
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=None)
    session.post = MagicMock(return_value=ctx)

    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )
    await controller.on_text("Hello")
    assert controller.phase == "aborted"
    assert controller.should_fallback_to_static is True


@pytest.mark.asyncio
async def test_controller_ignores_text_after_terminal() -> None:
    """终态后 on_text 被忽略"""
    session = _mock_session({"id": "smid_abc"})
    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )
    await controller.on_text("Hello")
    await controller.complete()
    count = session.post.call_count
    # 终态后再调 on_text 应被忽略
    await controller.on_text("world")
    assert session.post.call_count == count


@pytest.mark.asyncio
async def test_controller_long_gap_batches_updates() -> None:
    """长间隔（>2s）后批量延迟 300ms flush"""
    session = _mock_session({"id": "smid_abc"})
    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )
    await controller.on_text("first")
    # 模拟长间隔
    controller._last_flush_time = time.monotonic() - 3.0
    old_flush_time = controller._last_flush_time
    # 长间隔后的首个 chunk 应更新 _last_flush_time + 延迟批量
    await controller.on_text("second")
    assert controller._last_flush_time > old_flush_time
    # 等待批量延迟执行
    await asyncio.sleep(0.4)
    assert session.post.call_count >= 2


# ─── 集成测试 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_integration_full_streaming_flow() -> None:
    """完整流式流程：启动 → 多次 patch → 终结"""
    session = _mock_session({"id": "smid_integration"})
    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )

    # 模拟 LLM 流式输出
    for chunk in ["Hello", " world", "!", " This", " is", " a", " test."]:
        await controller.on_text(chunk)
        await asyncio.sleep(0.05)

    # 等待节流完成
    await asyncio.sleep(0.7)

    # 完成流式
    await controller.complete()
    assert controller.phase == "completed"
    assert controller.should_fallback_to_static is False
    # 最终累积文本完整
    assert controller.accumulated_text == "Hello world! This is a test."
    # 应发送过多个分片（启动 + 若干 patch + DONE）
    assert session.post.call_count >= 2
    # 最后一个分片是 DONE
    last_body = session.post.call_args[1]["json"]
    assert last_body["input_state"] == STREAM_INPUT_STATE_DONE


@pytest.mark.asyncio
async def test_integration_abort_mid_stream() -> None:
    """流式中途中止：不发 DONE，状态为 aborted"""
    session = _mock_session({"id": "smid_abort"})
    controller = QQStreamingController(
        session=session, token="token_abc", openid="openid_xyz",
        msg_id="msg_001",
    )
    await controller.on_text("Hello")
    await asyncio.sleep(0.6)
    # 中止
    await controller.abort("cancelled by user")
    assert controller.phase == "aborted"
    # should_fallback 为 False（已成功发过启动分片）
    assert controller.should_fallback_to_static is False
