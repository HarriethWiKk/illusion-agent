"""微信渠道适配器
================

实现 WeixinChannel，对接腾讯 iLink Bot API，通过 HTTP 长轮询收消息。

核心职责：
    - 长轮询拉取消息（getupdates）
    - 准入控制（自回显/机器人/群消息丢弃）
    - context_token 管理（iLink 硬约束：每 peer 回复必须回传）
    - 打字状态（sendtyping）
    - 消息发送（sendmessage + 分片）

类说明：
    - WeixinChannel: 微信渠道实现
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, AsyncIterator

from illusion.channels.base import Channel, InboundMessage

if TYPE_CHECKING:
    from illusion.channels.config import WeixinChannelConfig
    from illusion.config.settings import Settings

logger = logging.getLogger(__name__)

# 重试参数
RETRY_DELAY_SECONDS = 2
BACKOFF_DELAY_SECONDS = 30
MAX_CONSECUTIVE_FAILURES = 3
SESSION_EXPIRED_ERRCODE = -14
SESSION_PAUSE_SECONDS = 600  # 会话过期后暂停 10 分钟


class WeixinChannel(Channel):
    """微信渠道实现（iLink Bot API）

    通过 HTTP 长轮询接收消息，不支持消息编辑（流式用打字状态替代）。

    Attributes:
        name: 渠道名 "weixin"
    """

    name = "weixin"

    def __init__(self, config: "WeixinChannelConfig", settings: "Settings") -> None:
        """初始化微信渠道

        Args:
            config: 微信配置
            settings: 主设置
        """
        super().__init__(config, settings)
        self._poll_session: Any = None  # 长轮询专用 session
        self._send_session: Any = None  # 发送专用 session（total=None 避免超时冲突）
        self._queue: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._loop: Any = None

        # context_token 管理（iLink 硬约束）
        self._context_tokens: dict[str, str] = {}  # user_id → context_token

        # 打字状态管理
        self._typing_tickets: dict[str, str] = {}  # user_id → ticket
        self._typing_ticket_times: dict[str, float] = {}  # user_id → 获取时间

        # 长轮询游标
        self._sync_buf: str = ""

        # bot 自身 account_id（用于自回显检测，用 account_id 而非 user_id）
        self._account_id: str = config.account_id

        # 消息去重
        self._seen_msg_ids: dict[str, float] = {}

    async def connect(self) -> None:
        """建立 HTTP 连接（长轮询 + 发送分离）"""
        import aiohttp  # 延迟导入

        from illusion.channels.weixin.ilink_api import _make_ssl_connector
        from illusion.config.i18n import t

        self._loop = asyncio.get_event_loop()
        connector = _make_ssl_connector()
        # 长轮询 session（有超时，35 秒 hold）
        self._poll_session = aiohttp.ClientSession(trust_env=True, connector=connector)
        # 发送 session（total=None，避免并发发送时 aiohttp 超时冲突）
        self._send_session = aiohttp.ClientSession(
            trust_env=True, connector=connector,
            timeout=aiohttp.ClientTimeout(total=None, connect=None, sock_connect=None, sock_read=None),
        )

        # 加载持久化状态
        self._load_context_tokens()
        self._load_sync_buf()

        print(t("channel_starting_weixin"))

    def _normalize(self, raw_msg: dict) -> InboundMessage | None:
        """把 iLink 入站消息标准化为 InboundMessage

        同时提取 context_token 并缓存（iLink 硬约束）。

        Args:
            raw_msg: iLink 原始消息 dict

        Returns:
            InboundMessage | None: 标准化消息，无法解析返回 None
        """
        try:
            user_id = raw_msg.get("from_user_id", "")
            if not user_id:
                return None

            # 提取并缓存 context_token
            ctx_token = raw_msg.get("context_token", "")
            if ctx_token:
                self._context_tokens[user_id] = ctx_token

            # 提取文本（从 item_list 的 type=1 项）
            text = ""
            for item in raw_msg.get("item_list", []):
                if item.get("type") == 1:  # ITEM_TEXT
                    text = item.get("text_item", {}).get("text", "")
                    break

            msg_id = raw_msg.get("msgid", "")
            is_bot = raw_msg.get("from_user_type") == "bot"

            return InboundMessage(
                text=text,
                chat_id=user_id,  # 微信私聊用 user_id 作为 chat_id
                chat_type="dm",  # 微信 bot 只私聊
                user_id=user_id,
                user_name="",
                message_id=msg_id,
                is_bot=is_bot,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("标准化微信消息失败: %s", exc)
            return None

    def _admit(self, msg: InboundMessage) -> bool:
        """准入控制：决定消息是否进入 agent

        微信 bot 只能私聊，准入极简（无群组策略）：
        1. 自回显 → 拒绝
        2. 其他机器人（allow_bots=False）→ 拒绝
        3. 群消息 → 拒绝（bot 身份限制）

        Args:
            msg: 标准化消息

        Returns:
            bool: 放行返回 True
        """
        # 1. 自回显（用 account_id 即 bot 身份，如 226d22c4ac3d@im.bot）
        if self._account_id and msg.user_id == self._account_id:
            return False
        # 2. 机器人策略
        if msg.is_bot and not self.config.allow_bots:
            return False
        # 3. 群消息直接丢弃
        if msg.chat_type == "group":
            return False
        return True

    async def listen(self) -> AsyncIterator[InboundMessage]:
        """长轮询监听消息"""
        logger.info("微信长轮询已启动，sync_buf=%s", repr(self._sync_buf[:30]) if self._sync_buf else "(空)")
        consecutive_failures = 0
        while not self._stop_event.is_set():
            try:
                result = await _poll_with_retry(
                    self._poll_session, base_url=self.config.base_url,
                    token=self.config.token, sync_buf=self._sync_buf,
                )
                consecutive_failures = 0

                # 更新游标
                self._sync_buf = result.get("get_updates_buf", self._sync_buf)
                self._save_sync_buf()

                # 处理消息
                msg_count = len(result.get("msgs", []))
                if msg_count:
                    logger.info("微信收到 %d 条消息", msg_count)
                for raw_msg in result.get("msgs", []):
                    msg = self._normalize(raw_msg)
                    if msg is None:
                        logger.debug("消息标准化失败，跳过")
                        continue
                    if self._is_duplicate(msg.message_id):
                        logger.debug("重复消息，跳过: %s", msg.message_id)
                        continue
                    if self._admit(msg):
                        logger.info("微信消息已准入，yield: user=%s text=%s", msg.user_id, msg.text[:30])
                        yield msg
                    else:
                        logger.info("微信消息被拒绝: user=%s is_bot=%s", msg.user_id, msg.is_bot)

            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                consecutive_failures += 1
                if consecutive_failures < MAX_CONSECUTIVE_FAILURES:
                    logger.warning("长轮询失败 (%d/3): %s，%ds 后重试",
                                   consecutive_failures, exc, RETRY_DELAY_SECONDS)
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                else:
                    logger.warning("连续失败 %d 次，%ds 退避", consecutive_failures, BACKOFF_DELAY_SECONDS)
                    await asyncio.sleep(BACKOFF_DELAY_SECONDS)
                    consecutive_failures = 0

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
        expired = [k for k, v in self._seen_msg_ids.items() if now - v > 300]
        for k in expired:
            del self._seen_msg_ids[k]
        if msg_id in self._seen_msg_ids:
            return True
        self._seen_msg_ids[msg_id] = now
        return False

    async def send_text(self, chat_id: str, text: str, *, reply_to: str = "") -> str:
        """发送文本消息，超长自动分片，含重试和限流退避

        Args:
            chat_id: 目标会话（微信用 user_id）
            text: 文本内容
            reply_to: 未使用（微信不支持回复引用）

        Returns:
            str: 空字符串（微信无 message_id 返回）
        """
        from illusion.channels.weixin.ilink_api import (
            send_message, _split_text, SESSION_EXPIRED_ERRCODE, RATE_LIMIT_ERRCODE,
        )

        chunks = _split_text(text)
        logger.info("微信发送 %d 个分片到 %s", len(chunks), chat_id)
        for i, chunk in enumerate(chunks):
            if i > 0:
                await asyncio.sleep(1.5)  # 分片间隔，防限流
            ctx_token = self._context_tokens.get(chat_id, "")

            # 重试逻辑（最多 3 次，处理瞬态失败和限流）
            for attempt in range(3):
                resp = await send_message(
                    self._send_session, base_url=self.config.base_url, token=self.config.token,
                    to=chat_id, text=chunk, context_token=ctx_token or None,
                    client_id=f"illusion-weixin-{uuid.uuid4().hex}",
                )
                errcode = resp.get("errcode", 0)
                if errcode == SESSION_EXPIRED_ERRCODE:
                    # 会话过期：去掉 context_token 降级重试一次
                    if attempt == 0:
                        ctx_token = ""
                        self._context_tokens.pop(chat_id, None)
                        logger.warning("微信会话过期，去掉 context_token 重试")
                        continue
                    from illusion.config.i18n import t
                    raise RuntimeError(t("weixin_session_expired"))
                if errcode == RATE_LIMIT_ERRCODE:
                    logger.warning("微信发送限流，%ds 后重试", RETRY_DELAY_SECONDS * 3)
                    await asyncio.sleep(RETRY_DELAY_SECONDS * 3)
                    continue
                if errcode != 0:
                    logger.warning("微信发送失败 (attempt %d/%d): errcode=%d",
                                   attempt + 1, 3, errcode)
                    if attempt < 2:
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                        continue
                break  # 成功或不可重试的错误

        self._save_context_tokens()
        return ""

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        """编辑消息——微信不支持编辑，空操作

        ChannelRunner 调此方法做流式更新时，对微信是 no-op。
        回复走 send_text 一次性发送。

        Args:
            chat_id: 会话标识
            message_id: 未使用
            text: 未使用
        """
        pass

    async def send_file(self, chat_id: str, file_path: str) -> None:
        """发送文件——本次不支持，记录日志

        Args:
            chat_id: 目标会话
            file_path: 本地文件路径
        """
        logger.info("微信渠道暂不支持文件发送: %s", file_path)

    async def start_typing(self, chat_id: str) -> None:
        """开始打字状态指示

        Args:
            chat_id: 目标 user_id
        """
        ticket = await self._ensure_typing_ticket(chat_id)
        if not ticket:
            return
        try:
            from illusion.channels.weixin.ilink_api import send_typing, TYPING_START
            await send_typing(
                self._send_session, base_url=self.config.base_url, token=self.config.token,
                to_user_id=chat_id, typing_ticket=ticket, status=TYPING_START,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("发送打字状态失败: %s", exc)

    async def stop_typing(self, chat_id: str) -> None:
        """停止打字状态指示

        Args:
            chat_id: 目标 user_id
        """
        ticket = await self._ensure_typing_ticket(chat_id)
        if not ticket:
            return
        try:
            from illusion.channels.weixin.ilink_api import send_typing, TYPING_STOP
            await send_typing(
                self._send_session, base_url=self.config.base_url, token=self.config.token,
                to_user_id=chat_id, typing_ticket=ticket, status=TYPING_STOP,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("停止打字状态失败: %s", exc)

    async def _ensure_typing_ticket(self, user_id: str) -> str:
        """获取打字 ticket（TTL 600s，过期自动刷新）

        移植 hermes issue #38085 修复：ticket 过期后 stop_typing 静默失效，
        导致用户端永远卡在「正在输入」。

        Args:
            user_id: 目标用户

        Returns:
            str: 打字 ticket，获取失败返回空串
        """
        cached = self._typing_tickets.get(user_id)
        cached_time = self._typing_ticket_times.get(user_id, 0)
        if cached and (time.monotonic() - cached_time < 600):
            return cached

        try:
            from illusion.channels.weixin.ilink_api import get_config
            ctx_token = self._context_tokens.get(user_id, "")
            cfg = await get_config(
                self._send_session, base_url=self.config.base_url,
                token=self.config.token, context_token=ctx_token,
                ilink_user_id=user_id,
            )
            ticket = cfg.get("typing_ticket", "")
            if ticket:
                self._typing_tickets[user_id] = ticket
                self._typing_ticket_times[user_id] = time.monotonic()
            return ticket
        except Exception as exc:  # noqa: BLE001
            logger.debug("获取打字 ticket 失败: %s", exc)
            return ""

    async def shutdown(self) -> None:
        """关闭渠道"""
        self._stop_event.set()
        if self._poll_session is not None:
            await self._poll_session.close()
        if self._send_session is not None:
            await self._send_session.close()

    # ─── 持久化 ──────────────────────────────────────────────

    def _load_context_tokens(self) -> None:
        """从磁盘加载 context_tokens"""
        from illusion.config.paths import get_channels_data_dir
        path = get_channels_data_dir() / "weixin" / "context_tokens.json"
        if path.exists():
            try:
                self._context_tokens = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                pass

    def _save_context_tokens(self) -> None:
        """持久化 context_tokens 到磁盘"""
        from illusion.config.paths import get_channels_data_dir
        path = get_channels_data_dir() / "weixin" / "context_tokens.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._context_tokens, ensure_ascii=False), encoding="utf-8")

    def _load_sync_buf(self) -> None:
        """从磁盘加载长轮询游标"""
        from illusion.config.paths import get_channels_data_dir
        path = get_channels_data_dir() / "weixin" / "sync_buf.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._sync_buf = data.get("sync_buf", "")
            except (json.JSONDecodeError, ValueError):
                pass

    def _save_sync_buf(self) -> None:
        """持久化游标到磁盘"""
        from illusion.config.paths import get_channels_data_dir
        path = get_channels_data_dir() / "weixin" / "sync_buf.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"sync_buf": self._sync_buf}), encoding="utf-8")


async def _poll_with_retry(
    session: Any,
    *,
    base_url: str,
    token: str,
    sync_buf: str,
) -> dict[str, Any]:
    """调用长轮询，处理会话过期错误码

    Args:
        session: aiohttp.ClientSession
        base_url: API 入口
        token: Bearer token
        sync_buf: 游标

    Returns:
        dict: 长轮询响应

    Raises:
        RuntimeError: 会话过期需重新扫码
    """
    from illusion.channels.weixin.ilink_api import poll_updates, SESSION_EXPIRED_ERRCODE

    result = await poll_updates(session, base_url=base_url, token=token, sync_buf=sync_buf)

    errcode = result.get("errcode", 0)
    ret = result.get("ret", 0)
    if errcode == SESSION_EXPIRED_ERRCODE or ret == SESSION_EXPIRED_ERRCODE:
        from illusion.config.i18n import t
        raise RuntimeError(t("weixin_session_expired"))

    return result
