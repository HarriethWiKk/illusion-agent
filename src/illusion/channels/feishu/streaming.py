"""飞书 CardKit 流式卡片控制器

管理单条飞书消息的流式卡片生命周期：
- 创建流式卡片（CardKit card.create + im.message.create）
- 节流更新 element（cardElement.content，100ms 间隔）
- 终态收尾：先 card.settings 关闭 streaming_mode，再 card.update 全卡替换
- CardKit 失败时降级到 patch_card（1500ms 节流）

状态机（5 态）：
    idle → creating → streaming → completed / error

参考实现：openclaw-lark 的 streaming-card-controller.js + flush-controller.js
关键点：
- 终态必须先 set_card_streaming_mode(False) 关闭流式态，再全卡替换
  （否则飞书客户端仍在流式态，导致终态卡片渲染异常）
- 长间隔批量分支必须更新 last_flush_time，避免后续事件反复取消+重设 timer
- needs_reflush 通过 pending_timer 互斥，不直接 create_task
- flush 前对 display_text 去重，避免无意义 API 调用
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Coroutine

from illusion.channels.feishu.messaging import (
    STREAMING_ELEMENT_ID,
    build_complete_card,
    build_display_text,
    build_streaming_card,
    create_card_entity,
    patch_card,
    send_card_by_card_id,
    set_card_streaming_mode,
    stream_card_element_content,
    update_cardkit_card,
)

logger = logging.getLogger(__name__)

# 节流常量（秒）—— 与 openclaw-lark THROTTLE_CONSTANTS 对齐
_THROTTLE_MS = 0.1  # CardKit: 100ms
_THROTTLE_PATCH_MS = 1.5  # patch 降级: 1500ms
_LONG_GAP_THRESHOLD_MS = 2.0  # 长间隔阈值
_BATCH_AFTER_GAP_MS = 0.3  # 长间隔后批量延迟

# 合法状态转换
_TRANSITIONS: dict[str, set[str]] = {
    "idle": {"creating"},
    "creating": {"streaming", "error"},
    "streaming": {"completed", "error"},
    "completed": set(),
    "error": set(),
}


class FeishuStreamingCardController:
    """管理单条飞书消息的流式卡片生命周期"""

    def __init__(
        self,
        client: Any,
        chat_id: str,
        *,
        reply_to: str = "",
    ) -> None:
        self._client = client
        self._chat_id = chat_id
        self._reply_to = reply_to

        # 状态机
        self._phase = "idle"

        # CardKit 资源
        self._message_id: str | None = None
        self._card_id: str = ""  # 空字符串表示 CardKit 不可用，走 patch 降级

        # 流式累积
        self._accumulated_text: str = ""
        self._reasoning_text: str = ""
        self._is_reasoning_phase: bool = False

        # 节流
        self._sequence: int = 0
        self._last_flush_time: float = 0.0
        self._pending_timer: asyncio.TimerHandle | None = None
        self._flush_in_progress: bool = False
        self._needs_reflush: bool = False
        self._card_message_ready: bool = False
        self._last_flushed_text: str = ""  # 去重：上次成功 flush 的文本

        # 计时
        self._start_time: float = 0.0
        self._reasoning_start_time: float = 0.0
        self._reasoning_elapsed_ms: int = 0

    # --- 公开属性 ---

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def message_id(self) -> str:
        return self._message_id or ""

    @property
    def card_id(self) -> str:
        return self._card_id

    @property
    def accumulated_text(self) -> str:
        return self._accumulated_text

    @property
    def reasoning_text(self) -> str:
        return self._reasoning_text

    @property
    def is_reasoning_phase(self) -> bool:
        return self._is_reasoning_phase

    # --- 状态机 ---

    def _transition(self, new_phase: str) -> bool:
        """尝试状态转换，非法转换返回 False"""
        if new_phase in _TRANSITIONS.get(self._phase, set()):
            old = self._phase
            self._phase = new_phase
            logger.debug("状态转换: %s → %s", old, new_phase)
            return True
        logger.warning("非法状态转换: %s → %s（拒绝）", self._phase, new_phase)
        return False

    # --- 生命周期入口 ---

    async def start(self) -> None:
        """创建流式卡片，进入 streaming 状态

        尝试 CardKit 路径，失败时降级到 patch 路径。
        """
        if not self._transition("creating"):
            return

        self._start_time = time.monotonic()

        # 尝试 CardKit 路径
        card_content = build_streaming_card()
        card_id = await create_card_entity(self._client, card_content)

        if card_id:
            # CardKit 成功，通过 card_id 发送消息
            try:
                message_id = await send_card_by_card_id(
                    self._client, self._chat_id, card_id, reply_to=self._reply_to,
                )
                self._card_id = card_id
                self._message_id = message_id
                self._transition("streaming")
                self._card_message_ready = True
                # 初始化时间戳，确保首个 throttledUpdate 进入节流窗口分支
                # （而不是被识别为长间隔立即 flush 只有 1-2 个字符）
                self._last_flush_time = time.monotonic()
                return
            except RuntimeError as exc:
                logger.warning("CardKit 消息发送失败，降级到 patch: %s", exc)

        # 降级到 patch 路径：发送普通卡片
        from illusion.channels.feishu.messaging import send_card
        from illusion.config.i18n import t as _t

        try:
            self._message_id = await send_card(
                self._client, self._chat_id, _t("feishu_thinking"),
                reply_to=self._reply_to,
            )
            self._card_id = ""  # 标记 CardKit 不可用
            self._transition("streaming")
            self._card_message_ready = True
            self._last_flush_time = time.monotonic()
        except Exception as exc:  # noqa: BLE001
            logger.error("降级路径也失败: %s", exc)
            self._transition("error")

    # --- 流式回调 ---

    async def on_reasoning(self, reasoning: str) -> None:
        """处理思考增量"""
        if self._phase != "streaming":
            return
        if self._reasoning_start_time == 0:
            self._reasoning_start_time = time.monotonic()
        self._is_reasoning_phase = True
        self._reasoning_text += reasoning
        await self._throttled_flush()

    async def on_text(self, text: str) -> None:
        """处理文本增量

        首个 text 到达时重置 is_reasoning_phase（参照 openclaw-lark onPartialReply），
        避免思考前缀残留到答案阶段。
        """
        if self._phase != "streaming":
            return
        if self._is_reasoning_phase:
            self._is_reasoning_phase = False
            if self._reasoning_start_time > 0:
                self._reasoning_elapsed_ms = int(
                    (time.monotonic() - self._reasoning_start_time) * 1000
                )
        self._accumulated_text += text
        await self._throttled_flush()

    # --- 终态 ---

    async def complete(self) -> None:
        """完成流式，全卡替换为终态"""
        if not self._transition("completed"):
            return
        await self._finalize(is_error=False)

    async def error(self, error_msg: str = "") -> None:
        """错误终态"""
        if not self._transition("error"):
            return
        if error_msg:
            self._accumulated_text += f"\n\n---\n**Error**: {error_msg}"
        await self._finalize(is_error=True)

    # --- 节流 flush ---

    async def _throttled_flush(self) -> None:
        """节流更新 streaming_content element

        参照 openclaw-lark FlushController.throttledUpdate：
        - 距上次 flush ≥ 节流间隔且非长间隔：立即 flush
        - 距上次 flush ≥ 节流间隔且长间隔（>2s）：更新时间戳 + 延迟 300ms 批量 flush
          （关键：必须更新时间戳，否则批量窗口内每个事件都反复取消+重设 timer）
        - 距上次 flush < 节流间隔：调度延迟 flush（如无 pending timer）
        """
        if not self._card_message_ready or self._phase != "streaming":
            return

        throttle = _THROTTLE_MS if self._card_id else _THROTTLE_PATCH_MS
        now = time.monotonic()
        elapsed = now - self._last_flush_time

        if elapsed >= throttle:
            self._cancel_pending_flush()
            if elapsed > _LONG_GAP_THRESHOLD_MS and self._last_flush_time > 0:
                # 长间隔后延迟批量，避免首帧只显示 1-2 个字符
                # 关键：更新 last_flush_time，让批量窗口内的后续事件进入节流窗口分支
                # （而不是反复进入长间隔分支取消+重设 timer，导致延迟无限延长）
                self._last_flush_time = now
                self._schedule_delayed_flush(_BATCH_AFTER_GAP_MS)
            else:
                await self._flush()
        else:
            # 节流窗口内：调度延迟 flush（已有 pending 则不重复调度）
            if self._pending_timer is None:
                delay = throttle - elapsed
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

        参照 openclaw-lark FlushController.flush：
        - flush 进行中又来新事件时标记 needsReflush，完成后调度立即再 flush
        - _last_flush_time 在 API 调用前后各更新一次
        - 文本未变化时跳过 API 调用（参照 performFlush 的 lastFlushedText 优化）
        """
        if self._flush_in_progress or self._phase != "streaming":
            if self._flush_in_progress:
                self._needs_reflush = True
            return

        # 计算显示文本（用于去重判断）
        display_text = build_display_text(
            self._accumulated_text,
            self._reasoning_text,
            self._is_reasoning_phase,
        )

        # 文本未变化则跳过（避免无意义 API 调用）
        if display_text == self._last_flushed_text:
            return

        self._flush_in_progress = True
        self._needs_reflush = False
        self._last_flush_time = time.monotonic()  # API 调用前更新
        try:
            if self._card_id:
                # CardKit 路径：增量更新 element
                self._sequence += 1
                ok = await stream_card_element_content(
                    self._client,
                    self._card_id,
                    STREAMING_ELEMENT_ID,
                    display_text,
                    self._sequence,
                )
                if ok:
                    self._last_flushed_text = display_text
            elif self._message_id:
                # patch 降级路径：全卡替换
                await patch_card(self._client, self._message_id, display_text)
                self._last_flushed_text = display_text
        finally:
            self._flush_in_progress = False
            self._last_flush_time = time.monotonic()  # API 完成后更新
            # 参照 openclaw-lark：通过 pending_timer 互斥调度 reflush，
            # 不直接 create_task（避免与已调度的 flush 冲突）
            if (
                self._needs_reflush
                and self._phase == "streaming"
                and self._pending_timer is None
            ):
                self._needs_reflush = False
                self._schedule_delayed_flush(0)

    async def _finalize(self, *, is_error: bool) -> None:
        """终态收尾：先关闭流式模式，再全卡替换

        参照 openclaw-lark 的 onIdle / closeStreamingAndUpdate：
        1. cancelPendingFlush + 等待进行中 flush
        2. set_card_streaming_mode(False) 关闭流式态（关键！）
        3. update_cardkit_card 全卡替换为终态卡片
        4. 失败时降级到 patch_card

        如果跳过步骤 2，飞书客户端仍在流式态（loading 动画不停、
        streaming_content 仍等待增量），会导致终态卡片渲染异常
        （如循环显示思考过程）。
        """
        # 取消 pending flush timer
        self._cancel_pending_flush()

        # 等待进行中的 flush 完成
        while self._flush_in_progress:
            await asyncio.sleep(0.01)

        # 重置思考阶段标志，避免终态卡片残留思考前缀
        self._is_reasoning_phase = False

        elapsed_ms = int((time.monotonic() - self._start_time) * 1000)

        if self._card_id:
            # 步骤 1：关闭流式模式（必须先于全卡替换）
            self._sequence += 1
            streaming_ok = await set_card_streaming_mode(
                self._client, self._card_id, False, self._sequence,
            )
            if not streaming_ok:
                logger.warning("关闭流式模式失败，继续尝试全卡替换")

            # 步骤 2：全卡替换为终态卡片
            card_content = build_complete_card(
                text=self._accumulated_text,
                reasoning_text=self._reasoning_text,
                elapsed_ms=elapsed_ms,
                is_error=is_error,
            )
            self._sequence += 1
            ok = await update_cardkit_card(
                self._client, self._card_id, card_content, self._sequence,
            )
            if not ok and self._message_id:
                # card.update 失败，降级到 patch_card（传纯文本，不是 JSON）
                logger.warning("card.update 失败，降级到 patch_card")
                await patch_card(self._client, self._message_id, self._accumulated_text)
        else:
            # patch 降级路径：传纯 markdown 文本（patch_card 内部会包装成卡片）
            if self._message_id:
                await patch_card(self._client, self._message_id, self._accumulated_text)
