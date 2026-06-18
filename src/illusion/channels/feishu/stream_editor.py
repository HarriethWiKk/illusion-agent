"""飞书流式编辑器
================

把 agent 的流式输出增量更新到单张飞书交互卡片，实现「打字机」效果。

设计要点（参考飞书卡片能力调研）：
    - 统一用交互卡片（interactive）承载所有回复
    - 卡片内用单个 markdown 元素，飞书客户端渲染 markdown（含表格/代码块）
    - 卡片用 message.patch 更新，无编辑次数限制（text 消息有 230072 限制）
    - 首个 delta 立即创建卡片，用户秒看到响应开始
    - 后续 delta 节流 patch（1.0s 间隔），避免触发频率限制

类说明：
    - FeishuStreamEditor: 流式编辑器（卡片模式）
"""
from __future__ import annotations

import time  # 节流计时
from typing import TYPE_CHECKING  # 类型检查

if TYPE_CHECKING:
    from illusion.channels.base import Channel  # 渠道接口


class FeishuStreamEditor:
    """把 agent 流式输出增量更新到单张飞书交互卡片

    统一用卡片承载：markdown 渲染（含表格）+ 无编辑次数限制的流式更新。

    Attributes:
        _channel: 渠道实例
        _chat_id: 目标会话
        _reply_to: 要回复的消息 ID
        _msg_id: 已创建的卡片消息 ID（首个 delta 时赋值）
        _buf: 累积的完整文本
        _last_edit: 上次 patch 的单调时间戳
    """

    _EDIT_INTERVAL = 1.0  # 节流间隔（秒），卡片无编辑次数限制，但需控制频率

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
        self._msg_id: str | None = None  # 卡片消息 ID
        self._buf = ""  # 累积文本
        self._last_edit = 0.0  # 上次更新时间

    async def on_delta(self, delta: str) -> None:
        """处理一段增量文本

        首次创建卡片，后续按节流间隔 patch 更新卡片内容。
        空增量或累积内容为空时跳过。

        Args:
            delta: 新增文本
        """
        if not delta:
            return  # 空增量跳过
        self._buf += delta  # 累积
        if not self._buf.strip():
            return  # 累积内容仅空白时跳过，等待实质内容
        now = time.monotonic()  # 当前时间
        if self._msg_id is None:
            # 首次：立即创建卡片（含 markdown 渲染）
            self._msg_id = await self._channel.send_text(
                self._chat_id, self._buf, reply_to=self._reply_to
            )
            self._last_edit = now
        elif now - self._last_edit >= self._EDIT_INTERVAL:
            # 超过节流间隔：patch 更新卡片
            await self._channel.edit_message(self._chat_id, self._msg_id, self._buf)
            self._last_edit = now

    async def finalize(self) -> None:
        """轮次结束时做最后一次 patch，确保完整文本落盘

        卡片模式下无需区分 markdown/text——整个回复始终在一张卡片里，
        finalize 只需做最后一次 patch 把剩余缓冲内容刷出。
        """
        if self._msg_id and self._buf:
            await self._channel.edit_message(self._chat_id, self._msg_id, self._buf)
