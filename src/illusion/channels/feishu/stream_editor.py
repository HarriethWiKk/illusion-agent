"""飞书流式编辑器
================

把 agent 的流式输出增量编辑到单条飞书消息，实现「打字机」效果。

设计要点：
    - 首个 delta 立即创建消息，用户秒看到响应开始
    - 后续 delta 节流编辑（0.8s 间隔），避免触发飞书 API 限流
    - finalize 做最后一次编辑，确保完整文本落盘

类说明：
    - FeishuStreamEditor: 流式编辑器
"""
from __future__ import annotations

import time  # 节流计时
from typing import TYPE_CHECKING  # 类型检查

if TYPE_CHECKING:
    from illusion.channels.base import Channel  # 渠道接口


class FeishuStreamEditor:
    """把 agent 流式输出增量编辑到单条飞书消息

    Attributes:
        _channel: 渠道实例
        _chat_id: 目标会话
        _reply_to: 要回复的消息 ID
        _msg_id: 已创建的消息 ID（首个 delta 时赋值）
        _buf: 累积的完整文本
        _last_edit: 上次编辑的单调时间戳
    """

    _EDIT_INTERVAL = 0.8  # 节流间隔（秒）

    def __init__(self, channel: "Channel", chat_id: str, reply_to: str) -> None:
        """初始化

        Args:
            channel: 渠道实例
            chat_id: 目标会话
            reply_to: 要回复的消息 ID
        """
        self._channel = channel  # 渠道
        self._chat_id = chat_id  # 会话
        self._reply_to = reply_to  # 回复目标
        self._msg_id: str | None = None  # 消息 ID
        self._buf = ""  # 累积文本
        self._last_edit = 0.0  # 上次编辑时间

    async def on_delta(self, delta: str) -> None:
        """处理一段增量文本

        首次创建消息，后续按节流间隔编辑。

        Args:
            delta: 新增文本
        """
        self._buf += delta  # 累积
        now = time.monotonic()  # 当前时间
        if self._msg_id is None:
            # 首次：立即创建消息
            self._msg_id = await self._channel.send_text(
                self._chat_id, self._buf, reply_to=self._reply_to
            )
            self._last_edit = now
        elif now - self._last_edit >= self._EDIT_INTERVAL:
            # 超过节流间隔：编辑
            await self._channel.edit_message(self._chat_id, self._msg_id, self._buf)
            self._last_edit = now

    async def finalize(self) -> None:
        """轮次结束时做最后一次编辑，确保完整文本落盘

        若从未收到 delta（_msg_id 为 None），则不做任何操作。
        """
        if self._msg_id and self._buf:
            await self._channel.edit_message(self._chat_id, self._msg_id, self._buf)
