"""QQ C2C 流式消息控制器
================================

管理单条 QQ C2C 消息的流式生命周期，通过 QQ 开放平台
`/v2/users/{openid}/stream_messages` API 实现打字机效果。

核心机制：
- 首次发送返回 stream_msg_id，后续分片复用该 ID 做全量替换
- input_mode="replace"：每次发送的都是当前完整文本
- input_state: GENERATING(1) 生成中 / DONE(10) 终结
- 500ms 节流
- 4 态状态机：idle → streaming → completed / aborted
- 降级：首次分片失败时 shouldFallbackToStatic=True，由上层走普通发送
- 不展示 reasoning
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Coroutine
from typing import Any

import aiohttp

from illusion.channels.qq.api import (
    STREAM_INPUT_STATE_DONE,
    STREAM_INPUT_STATE_GENERATING,
    _next_msg_seq,
    send_c2c_stream_message,
)

logger = logging.getLogger(__name__)

# 节流常量（秒）
_THROTTLE_MS = 0.5  # 默认节流间隔 500ms
_LONG_GAP_THRESHOLD_MS = 2.0  # 长间隔阈值
_BATCH_AFTER_GAP_MS = 0.3  # 长间隔后批量延迟

# 合法状态转换
# idle → completed：LLM 无输出时直接完成（降级到静态发送）
_TRANSITIONS: dict[str, set[str]] = {
    "idle": {"streaming", "completed", "aborted"},
    "streaming": {"completed", "aborted"},
    "completed": set(),
    "aborted": set(),
}


class QQStreamingController:
    """管理单条 QQ C2C 消息的流式生命周期

    仅支持 C2C 私聊场景。群聊不支持 stream_messages API，由上层走普通发送。
    """

    def __init__(
        self,
        session: Any,
        token: str,
        openid: str,
        *,
        msg_id: str,
    ) -> None:
        self._session = session
        self._token = token
        self._openid = openid
        self._msg_id = msg_id  # 引用的入站消息 ID（被动消息定位 + event_id 复用）

        # 状态机
        self._phase = "idle"

        # 流式会话资源
        self._stream_msg_id: str = ""  # 首次发送后由服务器返回
        self._msg_seq: int = _next_msg_seq()  # 同一流式会话内共享
        self._index: int = 0  # 分片序号，递增
        self._sent_chunk_count: int = 0  # 已成功发送的分片数

        # 累积文本（不展示 reasoning，只累积 answer text）
        self._accumulated_text: str = ""

        # 节流
        self._last_flush_time: float = 0.0
        self._pending_timer: asyncio.TimerHandle | None = None
        self._flush_in_progress: bool = False
        self._needs_reflush: bool = False
        self._started: bool = False  # 是否已发送首个分片
        self._last_flushed_text: str = ""  # 去重：上次成功 flush 的文本

        # fire-and-forget 强引用集合（_create_background_task 创建的 task 在此保持引用）
        self._dispatch_tasks: set[asyncio.Task[None]] = set()

    # --- 公开属性 ---

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def stream_msg_id(self) -> str:
        return self._stream_msg_id

    @property
    def should_fallback_to_static(self) -> bool:
        """是否应降级到普通静态消息发送

        触发条件：进入终态时从未成功发出任何流式分片。
        """
        return self._phase in ("completed", "aborted") and self._sent_chunk_count == 0

    @property
    def accumulated_text(self) -> str:
        return self._accumulated_text

    # --- 状态机 ---

    def _transition(self, new_phase: str) -> bool:
        """尝试状态转换，非法转换返回 False"""
        if new_phase in _TRANSITIONS.get(self._phase, set()):
            old = self._phase
            self._phase = new_phase
            logger.debug("QQ 流式状态转换: %s → %s", old, new_phase)
            return True
        logger.warning("QQ 流式非法状态转换: %s → %s（拒绝）", self._phase, new_phase)
        return False

    # --- 流式回调 ---

    async def on_text(self, text: str) -> None:
        """处理文本增量（不展示 reasoning，只累积 answer text）

        参照 openclaw-main StreamingController.onPartialReply：
        - 累积全量文本
        - 首次有非空白文本时启动流式会话
        - 节流 patch
        """
        if self._phase not in ("idle", "streaming"):
            return
        if not text:
            return
        self._accumulated_text += text
        # 首次有非空白文本时启动流式会话
        if not self._started and self._accumulated_text.strip():
            await self._ensure_started()
        if self._phase != "streaming":
            return
        await self._throttled_flush()

    async def _ensure_started(self) -> None:
        """启动流式会话：发送首个分片（input_state=GENERATING）

        首次发送不传 stream_msg_id，服务器返回 id 字段（流式消息 ID）后保存。
        参照 openclaw-main streaming-c2c.ts:1007 doStartStreaming：
        响应字段名是 `id`（不是 `stream_msg_id`，请求体里才叫 stream_msg_id）。
        提取失败时抛异常 → aborted → 上层降级到静态发送。
        """
        if self._started:
            return
        self._started = True
        if not self._transition("streaming"):
            return
        self._last_flush_time = time.monotonic()
        try:
            # 参考openclaw-main streaming-c2c.ts:1034: const currentIndex = this.streamIndex++;
            # 首帧 index=0（后递增），QQ 协议要求从 0 开始
            current_index = self._index
            self._index += 1
            resp = await send_c2c_stream_message(
                self._session,
                self._token,
                self._openid,
                content=self._accumulated_text,
                input_state=STREAM_INPUT_STATE_GENERATING,
                msg_id=self._msg_id,
                msg_seq=self._msg_seq,
                index=current_index,
                # event_id 必填：参考 openclaw-main outbound-dispatch.ts:403 用入站 messageId 同值
                event_id=self._msg_id,
            )
            # 关键：QQ API 响应字段名是 `id`，不是 `stream_msg_id`
            # 参照 openclaw-main types.ts:60 MessageResponse.id
            stream_msg_id = str(resp.get("id", "") or "")
            if not stream_msg_id:
                # 提取失败：服务器返回了 2xx 但没有 id 字段，可能是 API 版本不兼容
                raise RuntimeError(
                    f"QQ stream_messages 响应缺少 id 字段: {resp}"
                )
            self._stream_msg_id = stream_msg_id
            self._sent_chunk_count += 1
            self._last_flushed_text = self._accumulated_text
            logger.info(
                "QQ 流式会话已启动: stream_msg_id=%s index=%d",
                self._stream_msg_id, self._index,
            )
        except (aiohttp.ClientError, RuntimeError, ValueError, KeyError) as exc:
            logger.warning("QQ 流式启动失败，将降级到静态发送: %s", exc)
            self._transition("aborted")

    # --- 终态 ---

    async def complete(self) -> None:
        """完成流式，发送终结分片（input_state=DONE）"""
        if not self._transition("completed"):
            return
        await self._finalize(is_error=False)

    async def abort(self, reason: str = "") -> None:
        """中止流式"""
        if not self._transition("aborted"):
            return
        if reason:
            logger.info("QQ 流式中止: %s", reason)
        # 中止时不发 DONE 分片，直接退出
        self._cancel_pending_flush()

    # --- 节流 flush ---

    async def _throttled_flush(self) -> None:
        """节流更新流式消息（全量替换）

        参照 openclaw-main FlushController.throttledUpdate：
        - 距上次 flush ≥ 500ms 且非长间隔：立即 flush
        - 距上次 flush ≥ 500ms 且长间隔（>2s）：更新时间戳 + 延迟 300ms 批量 flush
        - 距上次 flush < 500ms：调度延迟 flush（如无 pending）
        """
        if self._phase != "streaming":
            return

        now = time.monotonic()
        elapsed = now - self._last_flush_time

        if elapsed >= _THROTTLE_MS:
            self._cancel_pending_flush()
            if elapsed > _LONG_GAP_THRESHOLD_MS and self._last_flush_time > 0:
                # 长间隔后延迟批量，避免首帧只显示少量字符
                self._last_flush_time = now
                self._schedule_delayed_flush(_BATCH_AFTER_GAP_MS)
            else:
                await self._flush()
        else:
            if self._pending_timer is None:
                delay = _THROTTLE_MS - elapsed
                self._schedule_delayed_flush(delay)

    def _schedule_delayed_flush(self, delay: float) -> None:
        """调度延迟 flush（已有 pending timer 则保留旧的，避免反复推迟）"""
        if self._pending_timer is not None:
            return
        loop = asyncio.get_running_loop()
        self._pending_timer = loop.call_later(delay, self._delayed_flush_callback)

    def _delayed_flush_callback(self) -> None:
        """call_later 回调：清除 timer 句柄并调度实际 flush 任务"""
        self._pending_timer = None
        self._create_background_task(self._delayed_flush_task())

    def _create_background_task(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        """创建 fire-and-forget task 并保留强引用，防止 GC 抢收。

        Args:
            coro: 要执行的协程

        Returns:
            创建的 task
        """
        task = asyncio.create_task(coro)
        self._dispatch_tasks.add(task)
        task.add_done_callback(self._dispatch_tasks.discard)
        return task

    async def _delayed_flush_task(self) -> None:
        """延迟 flush 任务：检查状态后执行 flush"""
        if self._phase != "streaming":
            return
        await self._flush()

    def _cancel_pending_flush(self) -> None:
        """取消 pending 的延迟 flush timer"""
        if self._pending_timer is not None:
            self._pending_timer.cancel()
            self._pending_timer = None

    async def _flush(self) -> None:
        """实际执行 flush（互斥 + needsReflush 补偿 + 文本去重）

        参照 openclaw-main FlushController.flush + performFlush：
        - flush 进行中又来新事件时标记 needsReflush，完成后调度立即再 flush
        - _last_flush_time 在 API 调用前后各更新一次
        - 文本未变化时跳过 API 调用
        """
        if self._flush_in_progress or self._phase != "streaming":
            if self._flush_in_progress:
                self._needs_reflush = True
            return

        # 文本未变化则跳过（避免无意义 API 调用）
        if self._accumulated_text == self._last_flushed_text:
            return

        self._flush_in_progress = True
        self._needs_reflush = False
        self._last_flush_time = time.monotonic()
        try:
            current_index = self._index
            self._index += 1
            await send_c2c_stream_message(
                self._session,
                self._token,
                self._openid,
                content=self._accumulated_text,
                input_state=STREAM_INPUT_STATE_GENERATING,
                msg_id=self._msg_id,
                msg_seq=self._msg_seq,
                index=current_index,
                stream_msg_id=self._stream_msg_id,
                event_id=self._msg_id,
            )
            self._sent_chunk_count += 1
            self._last_flushed_text = self._accumulated_text
        except (aiohttp.ClientError, RuntimeError, ValueError, KeyError) as exc:
            logger.warning("QQ 流式 patch 失败（保留会话，继续尝试）: %s", exc)
        finally:
            self._flush_in_progress = False
            self._last_flush_time = time.monotonic()
            # 通过 pending_timer 互斥调度 reflush
            if (
                self._needs_reflush
                and self._phase == "streaming"
                and self._pending_timer is None
            ):
                self._needs_reflush = False
                self._schedule_delayed_flush(0)

    async def _finalize(self, *, is_error: bool) -> None:
        """终态收尾：发送最后分片（input_state=DONE）

        参照 openclaw-main StreamingController.finalizeOnIdle：
        1. cancelPendingFlush + 等待进行中 flush
        2. 若有活跃 stream_msg_id → 发送 DONE 分片
        3. 若从未发过任何分片 → should_fallback_to_static=True（上层降级）

        与飞书不同：QQ 终态就是发送一个 input_state=DONE 的分片，
        内容为当前累积全量文本。不需要"全卡替换"。
        """
        self._cancel_pending_flush()

        # 等待进行中的 flush 完成
        while self._flush_in_progress:
            await asyncio.sleep(0.01)

        # 从未成功发出任何分片 → 降级（上层会走普通 send_text）
        if self._sent_chunk_count == 0:
            logger.info("QQ 流式从未发出分片，将降级到静态发送")
            return

        # 发送终结分片
        try:
            current_index = self._index
            self._index += 1
            await send_c2c_stream_message(
                self._session,
                self._token,
                self._openid,
                content=self._accumulated_text,
                input_state=STREAM_INPUT_STATE_DONE,
                msg_id=self._msg_id,
                msg_seq=self._msg_seq,
                index=current_index,
                stream_msg_id=self._stream_msg_id,
                event_id=self._msg_id,
            )
            self._sent_chunk_count += 1
            logger.info(
                "QQ 流式已完成: stream_msg_id=%s 总分片数=%d 文本长度=%d",
                self._stream_msg_id, self._sent_chunk_count, len(self._accumulated_text),
            )
        except (aiohttp.ClientError, RuntimeError, ValueError, KeyError) as exc:
            logger.warning("QQ 流式终结分片发送失败: %s", exc)
