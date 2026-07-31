# tests/channels/qq/test_qq_streaming.py
"""QQStreamingController 单元测试"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from illusion.channels.base_streaming import StreamState
from illusion.channels.qq.streaming import QQStreamingController
from illusion.config.i18n import t as _t


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_token():
    return "test_token"


@pytest.fixture
def mock_openid():
    return "test_openid"


@pytest.fixture
def mock_msg_id():
    return "test_msg_id"


@pytest.fixture
def controller(mock_session, mock_token, mock_openid, mock_msg_id):
    return QQStreamingController(
        session=mock_session,
        token=mock_token,
        openid=mock_openid,
        msg_id=mock_msg_id,
    )


@pytest.fixture
async def streaming_controller(controller):
    """返回已启动流式会话的控制器"""
    with patch("illusion.channels.qq.streaming.send_c2c_stream_message") as mock_send:
        mock_send.return_value = {"id": "stream-123"}
        await controller.start()
    return controller


class TestQQStreamingControllerInit:
    def test_inherits_base(self, controller):
        from illusion.channels.base_streaming import BaseStreamingController
        assert isinstance(controller, BaseStreamingController)

    def test_throttle_is_500ms(self, controller):
        assert controller._throttle_seconds == 0.5

    def test_initial_stream_msg_id_empty(self, controller):
        assert controller.stream_msg_id == ""


class TestQQDoFlush:
    @pytest.mark.asyncio
    async def test_first_flush_returns_stream_msg_id(self, controller):
        with patch("illusion.channels.qq.streaming.send_c2c_stream_message") as mock_send:
            mock_send.return_value = {"id": "stream-123"}
            await controller._do_flush("hello", StreamState.GENERATING)

            mock_send.assert_called_once()
            assert controller.stream_msg_id == "stream-123"

    @pytest.mark.asyncio
    async def test_subsequent_flush_uses_stream_msg_id(self, controller):
        with patch("illusion.channels.qq.streaming.send_c2c_stream_message") as mock_send:
            mock_send.return_value = {"id": "stream-123"}

            await controller._do_flush("first", StreamState.GENERATING)
            await controller._do_flush("second", StreamState.GENERATING)

            assert mock_send.call_count == 2
            # 第二次调用应包含 stream_msg_id
            second_call = mock_send.call_args_list[1]
            assert second_call.kwargs.get("stream_msg_id") == "stream-123"

    @pytest.mark.asyncio
    async def test_flush_without_id_raises(self, controller):
        with patch("illusion.channels.qq.streaming.send_c2c_stream_message") as mock_send:
            mock_send.return_value = {}  # 无 id

            with pytest.raises(RuntimeError, match="缺少 id 字段"):
                await controller._do_flush("test", StreamState.GENERATING)


class TestQQDoFinalize:
    @pytest.mark.asyncio
    async def test_finalize_sends_done_state(self, controller):
        with patch("illusion.channels.qq.streaming.send_c2c_stream_message") as mock_send:
            mock_send.return_value = {"id": "stream-123"}

            # 先 flush 一次获取 stream_msg_id
            await controller._do_flush("test", StreamState.GENERATING)
            await controller._do_finalize(is_error=False)

            # 最后一次调用应是 DONE 状态
            last_call = mock_send.call_args_list[-1]
            assert last_call.kwargs.get("input_state") == 10  # DONE


class TestQQReasoningSupport:
    @pytest.mark.asyncio
    async def test_reasoning_updates_text(self, streaming_controller):
        await streaming_controller.on_reasoning("thinking...")
        assert streaming_controller.reasoning_text == "thinking..."
        assert streaming_controller.is_reasoning_phase is True

    @pytest.mark.asyncio
    async def test_reasoning_shows_in_display(self, streaming_controller):
        await streaming_controller.on_reasoning("thinking...")
        display = streaming_controller._build_display_text()
        thinking_header = _t("streaming_thinking")
        assert thinking_header in display
        assert "thinking..." in display

    @pytest.mark.asyncio
    async def test_text_keeps_reasoning_visible(self, streaming_controller):
        """reasoning 阶段结束后仍保留 reasoning 文本（QQ 前缀兼容）"""
        await streaming_controller.on_reasoning("thinking")
        await streaming_controller.on_text("answer")

        assert streaming_controller.is_reasoning_phase is False
        display = streaming_controller._build_display_text()
        thinking_header = _t("streaming_thinking")
        assert display == f"{thinking_header}\n\nthinking\n\n---\n\nanswer"
