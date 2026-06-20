"""QQ 渠道适配器
================

实现 QQChannel，对接 QQ 开放平台 Bot API v2，通过 WebSocket 网关收消息。

核心职责：
    - WebSocket 连接管理（心跳/重连）
    - 消息标准化（C2C/群聊 → InboundMessage）
    - 准入控制（自回显/机器人/群组策略）
    - 消息发送（文本/分片）
    - 打字状态指示

类说明：
    - QQChannel: QQ 渠道实现
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, AsyncIterator

from illusion.channels.base import Channel, InboundMessage
from illusion.channels.qq.api import (
    MAX_MESSAGE_LENGTH,
    DEDUP_WINDOW_SECONDS,
    DEDUP_MAX_SIZE,
    ensure_token,
    send_c2c_message,
    send_group_message,
    split_text,
    strip_markdown,
)

if TYPE_CHECKING:
    from illusion.channels.config import QQChannelConfig
    from illusion.config.settings import Settings

logger = logging.getLogger(__name__)


class QQChannel(Channel):
    """QQ 渠道实现（QQ Bot API v2）

    通过 WebSocket 网关接收消息，支持 C2C 私聊和群聊。

    Attributes:
        name: 渠道名 "qq"
    """

    name = "qq"

    def __init__(self, config: "QQChannelConfig", settings: "Settings") -> None:
        """初始化 QQ 渠道

        Args:
            config: QQ 配置
            settings: 主设置
        """
        super().__init__(config, settings)
        self._queue: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._ws_client: Any = None  # QQWSClient 实例
        self._session: Any = None  # aiohttp.ClientSession（发送用）
        self._token: str = ""

        # bot 自身 openid（用于自回显检测）
        self._bot_openid: str = ""

        # 消息去重
        self._seen_msg_ids: dict[str, float] = {}

        # 打字状态防抖
        self._last_typing_time: float = 0.0
        self._typing_debounce: float = 50.0

        # chat_type 缓存（用于判断 C2C vs 群聊）
        self._chat_type_cache: dict[str, str] = {}

        # markdown 支持（从配置读取，默认启用）
        self._markdown_support: bool = getattr(config, "markdown_support", True)

    async def connect(self) -> None:
        """建立 WS 连接和 HTTP session"""
        import aiohttp

        from illusion.channels.qq.ws_client import QQWSClient
        from illusion.config.i18n import t

        self._session = aiohttp.ClientSession(trust_env=True)
        self._ws_client = QQWSClient(
            app_id=self.config.app_id,
            client_secret=self.config.client_secret,
            on_event=self._on_ws_event,
        )
        await self._ws_client.connect()

        print(t("channel_starting_qq"))

    async def _on_ws_event(self, event_type: str, data: dict[str, Any]) -> None:
        """WS 事件回调，标准化后放入队列

        Args:
            event_type: 事件类型（如 C2C_MESSAGE_CREATE）
            data: 事件数据
        """
        msg: InboundMessage | None = None

        if event_type == "C2C_MESSAGE_CREATE":
            msg = self._normalize_c2c(data)
        elif event_type == "GROUP_AT_MESSAGE_CREATE":
            logger.debug("QQ 群聊原始事件: id=%s, content=%s, group=%s",
                         data.get("id"), repr(data.get("content")),
                         data.get("group_openid"))
            msg = self._normalize_group(data)

        if msg is None:
            return

        if self._is_duplicate(msg.message_id):
            logger.debug("QQ 重复消息，跳过: %s", msg.message_id)
            return

        if self._admit(msg):
            # 空 @消息（只 @机器人没有文字）→ 回复帮助提示，不传给 LLM
            if not msg.text.strip() and msg.chat_type == "group":
                logger.info("QQ 空 @消息，回复帮助提示: user=%s", msg.user_id)
                from illusion.config.i18n import t as _t
                await self.send_text(msg.chat_id, _t("feishu_cmd_help"),
                                     reply_to=msg.message_id)
                return

            logger.info("QQ 消息已准入: user=%s text=%s", msg.user_id, msg.text[:30])
            self._queue.put_nowait(msg)
        else:
            logger.info("QQ 消息被拒绝: user=%s is_bot=%s", msg.user_id, msg.is_bot)

    def _normalize_c2c(self, raw: dict[str, Any]) -> InboundMessage | None:
        """标准化 C2C 私聊消息

        Args:
            raw: QQ API 原始消息数据

        Returns:
            InboundMessage | None: 标准化消息，无法解析返回 None
        """
        try:
            msg_id = str(raw.get("id", ""))
            content = str(raw.get("content", "")).strip()
            author = raw.get("author") if isinstance(raw.get("author"), dict) else {}
            user_id = str(author.get("id", ""))
            user_name = str(author.get("username", ""))

            if not msg_id or not user_id:
                return None

            # 缓存 chat_type
            self._chat_type_cache[user_id] = "dm"

            return InboundMessage(
                text=content,
                chat_id=user_id,  # C2C 用 user_id 作为 chat_id
                chat_type="dm",
                user_id=user_id,
                user_name=user_name,
                message_id=msg_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("标准化 QQ C2C 消息失败: %s", exc)
            return None

    def _normalize_group(self, raw: dict[str, Any]) -> InboundMessage | None:
        """标准化群聊消息

        群聊消息需要去除 @机器人 的文本前缀。

        Args:
            raw: QQ API 原始消息数据

        Returns:
            InboundMessage | None: 标准化消息，无法解析返回 None
        """
        try:
            msg_id = str(raw.get("id", ""))
            content = str(raw.get("content", "")).strip()
            author = raw.get("author") if isinstance(raw.get("author"), dict) else {}
            user_id = str(author.get("id", ""))
            user_name = str(author.get("username", ""))
            group_openid = str(raw.get("group_openid", ""))

            if not msg_id or not user_id or not group_openid:
                logger.warning("QQ 群聊消息缺少必填字段: msg_id=%s user_id=%s group=%s",
                               repr(msg_id), repr(user_id), repr(group_openid))
                return None

            # 去除 @mention 前缀
            mentions = raw.get("mentions", [])
            for mention in mentions:
                mention_id = str(mention.get("id", ""))
                mention_name = str(mention.get("username", ""))
                # QQ @mention 格式: <@!bot_id> 或 @username
                for prefix in [f"<@!{mention_id}>", f"@{mention_name}"]:
                    if content.startswith(prefix):
                        content = content[len(prefix):].strip()
                        break

            # 缓存 chat_type
            self._chat_type_cache[group_openid] = "group"

            return InboundMessage(
                text=content,
                chat_id=group_openid,
                chat_type="group",
                user_id=user_id,
                user_name=user_name,
                message_id=msg_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("标准化 QQ 群聊消息失败: %s", exc)
            return None

    def _admit(self, msg: InboundMessage) -> bool:
        """准入控制：决定消息是否进入 agent

        准入规则：
        1. 自回显 → 拒绝
        2. 机器人消息（allow_bots=False）→ 拒绝
        3. 私聊 → 放行
        4. 群聊 → 检查群组策略

        Args:
            msg: 标准化消息

        Returns:
            bool: 放行返回 True
        """
        # 1. 自回显
        if self._bot_openid and msg.user_id == self._bot_openid:
            return False

        # 2. 机器人策略
        if msg.is_bot and not self.config.allow_bots:
            return False

        # 3. 私聊直接放行
        if msg.chat_type == "dm":
            return True

        # 4. 群聊策略
        policy = self.config.group_policy

        # 管理员永远放行
        if msg.user_id in policy.admin_list:
            return True

        if policy.mode == "disabled":
            return False

        if policy.mode == "allowlist":
            return msg.chat_id in policy.allowlist

        if policy.mode == "blacklist":
            return msg.chat_id not in policy.blacklist

        # mode == "open"
        return True

    def _is_duplicate(self, msg_id: str) -> bool:
        """消息去重（msg_id + 5 分钟 TTL）

        Args:
            msg_id: 消息 ID

        Returns:
            bool: 重复返回 True
        """
        if not msg_id:
            return False
        now = time.monotonic()
        # 清理过期记录
        expired = [k for k, v in self._seen_msg_ids.items() if now - v > DEDUP_WINDOW_SECONDS]
        for k in expired:
            del self._seen_msg_ids[k]
        # 超过容量限制时清理最旧的
        if len(self._seen_msg_ids) >= DEDUP_MAX_SIZE:
            oldest = min(self._seen_msg_ids, key=lambda k: self._seen_msg_ids[k])
            del self._seen_msg_ids[oldest]
        if msg_id in self._seen_msg_ids:
            return True
        self._seen_msg_ids[msg_id] = now
        return False

    async def listen(self) -> AsyncIterator[InboundMessage]:
        """异步迭代器，不断 yield 入站消息"""
        logger.info("QQ 监听已启动")
        while not self._stop_event.is_set():
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield msg
            except asyncio.TimeoutError:
                continue

    def _format_message(self, content: str) -> str:
        """格式化消息内容

        markdown_support=True 时原样传递（QQ 自行渲染），
        False 时剥离 markdown 格式为纯文本。

        Args:
            content: 原始消息内容

        Returns:
            str: 格式化后的消息
        """
        if self._markdown_support:
            return content
        return strip_markdown(content)

    async def send_text(self, chat_id: str, text: str, *, reply_to: str = "") -> str:
        """发送文本消息，超长自动分片（代码块感知）

        markdown_support=True 时使用 markdown 信封（msg_type=2），
        分片时自动处理代码块围栏的闭合与重开。

        Args:
            chat_id: 目标会话（openid 或 group_openid）
            text: 文本内容
            reply_to: 引用的消息 ID（可选）

        Returns:
            str: 发送的消息 ID（QQ API 不返回则为空串）
        """
        if not self._session:
            return ""

        # 确保 token 有效
        if not self._token:
            self._token = await ensure_token(
                self._session, self.config.app_id, self.config.client_secret,
            )

        # 格式化（markdown 原样传递 or 剥离为纯文本）
        formatted = self._format_message(text)
        chunks = split_text(formatted, MAX_MESSAGE_LENGTH)
        logger.info("QQ 发送 %d 个分片到 %s (markdown=%s, reply_to=%s)",
                     len(chunks), chat_id, self._markdown_support, repr(reply_to))

        is_group = self._chat_type_cache.get(chat_id) == "group"

        # QQ 群聊 API 要求 msg_id（被动消息），无 msg_id 时跳过（主动消息无权限）
        if is_group and not reply_to:
            logger.warning("QQ 群聊发送跳过：缺少 msg_id（主动消息无权限）")
            return ""

        for i, chunk in enumerate(chunks):
            if i > 0:
                await asyncio.sleep(1.5)  # 分片间隔，防限流

            for attempt in range(3):
                try:
                    if is_group:
                        await send_group_message(
                            self._session, self._token, chat_id, chunk,
                            msg_id=reply_to,
                            markdown=self._markdown_support,
                        )
                    else:
                        await send_c2c_message(
                            self._session, self._token, chat_id, chunk,
                            msg_id=reply_to or "",
                            markdown=self._markdown_support,
                        )
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.warning("QQ 发送失败 (attempt %d/3): %s", attempt + 1, exc)
                    if attempt < 2:
                        await asyncio.sleep(2)
                    else:
                        raise

        return ""

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        """编辑消息——QQ 不支持编辑，空操作"""
        pass

    async def send_file(self, chat_id: str, file_path: str) -> None:
        """发送文件（三步分片上传）

        Args:
            chat_id: 目标会话
            file_path: 本地文件路径
        """
        try:
            from illusion.channels.qq.api import upload_file
            is_group = self._chat_type_cache.get(chat_id) == "group"
            await upload_file(
                self._session, self._token, chat_id, file_path,
                is_group=is_group,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("QQ 文件发送失败: %s", exc)

    async def start_typing(self, chat_id: str) -> None:
        """开始打字状态指示（C2C only，50s 防抖）

        Args:
            chat_id: 目标会话
        """
        now = time.monotonic()
        if now - self._last_typing_time < self._typing_debounce:
            return
        self._last_typing_time = now

        try:
            from illusion.channels.qq.api import send_typing
            if self._token:
                await send_typing(self._session, self._token, chat_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("QQ 打字状态发送失败: %s", exc)

    async def stop_typing(self, chat_id: str) -> None:
        """停止打字状态指示——QQ API 无停止接口，空操作"""
        pass

    async def shutdown(self) -> None:
        """关闭渠道"""
        self._stop_event.set()
        if self._ws_client:
            await self._ws_client.close()
        if self._session:
            await self._session.close()
