"""飞书渠道适配器
================

实现 FeishuChannel，对接飞书开放平台的 WS 长连接，处理事件分发与准入控制。

核心职责：
    - 建立 WS 长连接（lark-oapi 官方客户端）
    - 标准化入站事件为 InboundMessage
    - 准入控制（自回显/机器人/@提及/群组策略）
    - 消息收发委托给 messaging 模块

类说明：
    - FeishuChannel: 飞书渠道实现
"""
from __future__ import annotations

import asyncio  # 异步
import logging  # 日志
from typing import TYPE_CHECKING, Any, AsyncIterator  # 类型

from illusion.channels.base import Channel, InboundMessage  # 基类与消息类型

if TYPE_CHECKING:
    from illusion.channels.config import FeishuChannelConfig  # 配置
    from illusion.config.settings import Settings  # 主设置

logger = logging.getLogger(__name__)  # 日志器


class FeishuChannel(Channel):
    """飞书渠道实现

    通过 WS 长连接接收飞书消息事件，标准化后产出 InboundMessage。

    Attributes:
        name: 渠道名 "feishu"
    """

    name = "feishu"  # 渠道名

    def __init__(self, config: "FeishuChannelConfig", settings: "Settings") -> None:
        """初始化飞书渠道

        Args:
            config: 飞书配置
            settings: 主设置
        """
        super().__init__(config, settings)
        self._client: Any = None  # lark 客户端
        self._ws: Any = None  # WS 包装
        self._queue: asyncio.Queue[InboundMessage] = asyncio.Queue()  # 入站队列
        self._bot_open_id: str = ""  # bot 自身 open_id（hydrate 后赋值）
        self._stop_event = asyncio.Event()  # 停止信号

    async def connect(self) -> None:
        """建立 WS 长连接"""
        from illusion.channels.feishu.messaging import build_lark_client
        from illusion.channels.feishu.ws_client import FeishuWSClient
        from illusion.config.i18n import t

        # 构造 lark 客户端
        self._client = build_lark_client(self.config)
        # 构造 WS 包装
        domain = "https://open.feishu.cn" if self.config.domain == "feishu" else "https://open.larksuite.com"
        self._ws = FeishuWSClient(
            app_id=self.config.app_id,
            app_secret=self.config.app_secret,
            event_handler=self._on_raw_event,
            domain=domain,
        )
        # 在 executor 线程跑阻塞的 start()
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, self._ws.start)
        print(t("channel_feishu_connected", bot=self._bot_open_id or "illusion"))

    def _on_raw_event(self, event: Any) -> None:
        """处理原始飞书事件（在 WS 客户端线程调用）

        event 是 lark-oapi 的强类型 P2ImMessageReceiveV1 对象。
        标准化为 InboundMessage 后线程安全地投递到入站队列。

        Args:
            event: 强类型事件对象（P2ImMessageReceiveV1）
        """
        try:
            msg = self._normalize(event)
            if msg is not None and self._admit(msg, mentioned_bot=self._event_mentions_bot(event)):
                # 线程安全地投递到 asyncio.Queue
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    return  # 无事件循环，忽略
                loop.call_soon_threadsafe(self._queue.put_nowait, msg)
        except Exception as exc:  # noqa: BLE001
            logger.exception("处理飞书事件异常: %s", exc)

    def _normalize(self, event: Any) -> InboundMessage | None:
        """把强类型飞书事件标准化为 InboundMessage

        事件对象结构（lark-oapi 强类型）：
            event.event.sender.sender_id.open_id / .sender_type
            event.event.message.chat_id / .chat_type / .message_id / .content

        Args:
            event: P2ImMessageReceiveV1 事件对象

        Returns:
            InboundMessage | None: 标准化消息，无法解析返回 None
        """
        try:
            data = getattr(event, "event", None)
            if data is None:
                return None
            sender = getattr(data, "sender", None)
            message = getattr(data, "message", None)
            if sender is None or message is None:
                return None

            # 发送者信息
            sender_id = getattr(sender, "sender_id", None)
            user_id = ""
            if sender_id is not None:
                # 优先 open_id，其次 union_id、user_id
                user_id = (getattr(sender_id, "open_id", None)
                           or getattr(sender_id, "union_id", None)
                           or getattr(sender_id, "user_id", None)
                           or "")
            sender_type = getattr(sender, "sender_type", "") or ""
            is_bot = sender_type == "app"

            # 消息信息
            chat_id = getattr(message, "chat_id", "") or ""
            chat_type_raw = getattr(message, "chat_type", "p2p") or "p2p"  # p2p 或 group
            message_id = getattr(message, "message_id", "") or ""
            content = getattr(message, "content", '{"text":""}') or '{"text":""}'
            text = _extract_text(content)

            return InboundMessage(
                text=text,
                chat_id=chat_id,
                chat_type="group" if chat_type_raw == "group" else "dm",
                user_id=user_id,
                user_name="",  # 飞书事件不直接带显示名，需另调 API 获取
                message_id=message_id,
                is_bot=is_bot,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("标准化飞书事件失败: %s", exc)
            return None

    def _event_mentions_bot(self, event: Any) -> bool:
        """检测事件是否 @了 bot

        事件对象的 message.mentions 是 MentionEvent 列表，
        每项有 .id（含 .open_id 等属性）或 .key/name。

        Args:
            event: P2ImMessageReceiveV1 事件对象

        Returns:
            bool: 是否 @了 bot
        """
        try:
            data = getattr(event, "event", None)
            if data is None:
                return False
            message = getattr(data, "message", None)
            if message is None:
                return False
            mentions = getattr(message, "mentions", None) or []
            if not mentions:
                return False
            if not self._bot_open_id:
                return True  # 未能 hydrate bot ID 时，有 mention 即认为 @了
            for m in mentions:
                # MentionEvent.id 是 UserId 对象，有 open_id 属性
                m_id = getattr(m, "id", None)
                if m_id is not None:
                    if getattr(m_id, "open_id", None) == self._bot_open_id:
                        return True
            return False
        except Exception:  # noqa: BLE001
            return False

    def _admit(self, msg: InboundMessage, *, mentioned_bot: bool) -> bool:
        """准入控制：决定消息是否进入 agent

        4 道闸门：自回显、机器人、群组策略、@提及。

        Args:
            msg: 标准化消息
            mentioned_bot: 是否 @了 bot

        Returns:
            bool: 放行返回 True
        """
        # 1. 自回显
        if self._bot_open_id and msg.user_id == self._bot_open_id:
            return False
        # 2. 机器人策略
        if msg.is_bot and not self.config.allow_bots:
            return False
        # 3. 私聊直接放行（不受群组策略与 @提及影响）
        if msg.chat_type == "dm":
            return True
        # 4. 群组：管理员永远放行
        policy = self.config.group_policy
        if msg.user_id in policy.admin_list:
            return True
        # 5. 群组策略
        if policy.mode == "disabled":
            return False
        if policy.mode == "allowlist" and msg.chat_id not in policy.allowlist:
            return False
        if policy.mode == "blacklist" and msg.chat_id in policy.blacklist:
            return False
        # 6. @提及门控
        if self.config.require_mention and not mentioned_bot:
            return False
        return True

    async def listen(self) -> AsyncIterator[InboundMessage]:
        """异步迭代入站消息"""
        while not self._stop_event.is_set():
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield msg
            except asyncio.TimeoutError:
                continue

    async def send_text(self, chat_id: str, text: str, *, reply_to: str = "") -> str:
        """发送文本消息"""
        from illusion.channels.feishu.messaging import send_text as _send
        return await _send(self._client, self.config, chat_id, text, reply_to=reply_to)

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        """编辑消息"""
        from illusion.channels.feishu.messaging import edit_message as _edit
        await _edit(self._client, chat_id, message_id, text)

    async def send_file(self, chat_id: str, file_path: str) -> None:
        """发送文件"""
        from illusion.channels.feishu.messaging import send_file as _send_f
        await _send_f(self._client, self.config, chat_id, file_path)

    async def shutdown(self) -> None:
        """关闭渠道"""
        self._stop_event.set()
        if self._ws is not None:
            self._ws.stop()


def _extract_text(content: str) -> str:
    """从飞书消息 content JSON 提取纯文本

    Args:
        content: content JSON 字符串

    Returns:
        str: 纯文本
    """
    import json
    try:
        data = json.loads(content)
        return data.get("text", "").strip()
    except (json.JSONDecodeError, AttributeError):
        return ""
