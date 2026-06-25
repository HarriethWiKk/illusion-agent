"""QQ Bot WebSocket 网关客户端
==============================

实现 QQ Bot API v2 的 WebSocket 协议：连接、鉴权、心跳、重连、事件分发。

协议要点：
    - op 10 (Hello): 服务端发送心跳间隔
    - op 2 (Identify): 客户端鉴权（首次连接）
    - op 6 (Resume): 客户端恢复会话（断线重连）
    - op 0 (Dispatch): 业务事件分发
    - op 1 (Heartbeat): 客户端定期心跳
    - op 7 (Server Reconnect): 服务端要求重连
    - op 9 (Invalid Session): 会话无效
    - op 11 (Heartbeat ACK): 心跳确认

参考：https://bot.q.qq.com/wiki/develop/api-v2/
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Awaitable

import aiohttp

from illusion.channels.qq.api import (
    RECONNECT_BACKOFF,
    RATE_LIMIT_DELAY,
    ensure_token,
    get_gateway_url,
)

logger = logging.getLogger(__name__)

# ── 意图位 ────────────────────────────────────────────────────

INTENT_DIRECT_MESSAGES = 1 << 12  # C2C 私聊
INTENT_GROUP_MESSAGES = 1 << 25   # 群聊 @消息

# ── 关闭码 ────────────────────────────────────────────────────

FATAL_CLOSE_CODES = {4001, 4002, 4010, 4011, 4012, 4013, 4014, 4914, 4915}
RECONNECT_CLOSE_CODES = {4006, 4007, 4009}
RATE_LIMIT_CODE = 4008
INVALID_TOKEN_CODE = 4004

QUICK_DISCONNECT_THRESHOLD = 5.0
MAX_QUICK_DISCONNECTS = 3


class QQCloseError(Exception):
    """WebSocket 关闭异常，携带关闭码和原因"""

    def __init__(self, code: int, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class QQWSClient:
    """QQ Bot WebSocket 网关客户端

    管理与 QQ Bot 网关的 WebSocket 连接，处理协议层逻辑，
    将业务事件通过回调传递给上层（QQChannel adapter）。

    Attributes:
        app_id: 应用 ID
        client_secret: 应用密钥
    """

    def __init__(
        self,
        app_id: str,
        client_secret: str,
        on_event: EventCallback,
    ) -> None:
        """初始化 WS 客户端

        Args:
            app_id: QQ 应用 ID
            client_secret: QQ 应用密钥
            on_event: 事件回调，接收 (event_type, data)
        """
        self.app_id = app_id
        self.client_secret = client_secret
        self._on_event = on_event

        # 连接状态
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._running = False

        # 协议状态
        self._heartbeat_interval: float = 30.0
        self._last_seq: int | None = None
        self._session_id: str = ""
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._listen_task: asyncio.Task[None] | None = None

    @property
    def is_connected(self) -> bool:
        """WS 是否处于连接状态"""
        return self._running and self._ws is not None and not self._ws.closed

    async def connect(self) -> None:
        """建立连接：获取 token → 获取网关 → 打开 WS → 启动监听"""
        self._session = aiohttp.ClientSession(trust_env=True)
        self._running = True

        try:
            await self._connect_ws()
        except Exception:
            self._running = False
            await self._cleanup()
            raise

    async def _connect_ws(self) -> None:
        """获取网关地址并打开 WebSocket"""
        assert self._session is not None
        token = await ensure_token(self._session, self.app_id, self.client_secret)
        gateway_url = await get_gateway_url(self._session, token)

        self._ws = await self._session.ws_connect(gateway_url)
        logger.info("QQ WS 已连接: %s", gateway_url)

        # 启动心跳和监听
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._listen_task = asyncio.create_task(self._listen_loop())

    async def close(self) -> None:
        """关闭连接"""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._listen_task:
            self._listen_task.cancel()
        await self._cleanup()

    async def _cleanup(self) -> None:
        """清理资源"""
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        self._ws = None
        self._session = None

    # ── 心跳 ──────────────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """定期发送心跳（op 1）"""
        try:
            while self._running and self.is_connected:
                await asyncio.sleep(self._heartbeat_interval)
                if not self.is_connected:
                    break
                payload = {"op": 1, "d": self._last_seq}
                await self._send_json(payload)
                logger.debug("QQ 心跳已发送, seq=%s", self._last_seq)
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("QQ 心跳异常: %s", exc)

    # ── 监听 ──────────────────────────────────────────────────

    async def _listen_loop(self) -> None:
        """读取 WS 帧并分发，断线后自动重连"""
        backoff_idx = 0
        connect_time = 0.0
        quick_disconnects = 0

        while self._running:
            try:
                connect_time = time.monotonic()
                await self._read_events()
                backoff_idx = 0
                quick_disconnects = 0
            except asyncio.CancelledError:
                return
            except QQCloseError as exc:
                if not self._running:
                    return

                # 快速断连检测
                duration = time.monotonic() - connect_time
                if duration < QUICK_DISCONNECT_THRESHOLD and connect_time > 0:
                    quick_disconnects += 1
                    if quick_disconnects >= MAX_QUICK_DISCONNECTS:
                        logger.error("QQ 快速断连次数过多，停止重连")
                        return
                else:
                    quick_disconnects = 0

                # 致命错误码
                if exc.code in FATAL_CLOSE_CODES:
                    logger.error("QQ WS 致命错误 code=%s，停止重连", exc.code)
                    return

                # Token 无效
                if exc.code == INVALID_TOKEN_CODE:
                    logger.warning("QQ token 无效，刷新后重连")
                    from illusion.channels.qq.api import _token_cache
                    _token_cache.pop(self.app_id, None)

                # 限流
                if exc.code == RATE_LIMIT_CODE:
                    logger.warning("QQ WS 限流，等待 %ds", RATE_LIMIT_DELAY)
                    await asyncio.sleep(RATE_LIMIT_DELAY)

                # 会话无效
                if exc.code in RECONNECT_CLOSE_CODES:
                    self._session_id = ""
                    self._last_seq = None

                # 重连
                backoff_idx = await self._reconnect(backoff_idx)

            except Exception as exc:  # noqa: BLE001
                logger.warning("QQ WS 监听异常: %s", exc)
                backoff_idx = await self._reconnect(backoff_idx)

    async def _reconnect(self, backoff_idx: int) -> int:
        """指数退避重连

        Args:
            backoff_idx: 当前退避索引

        Returns:
            int: 下一个退避索引
        """
        if not self._running:
            return backoff_idx

        delay = RECONNECT_BACKOFF[min(backoff_idx, len(RECONNECT_BACKOFF) - 1)]
        logger.info("QQ WS 将在 %ds 后重连 (attempt %d)", delay, backoff_idx + 1)
        await asyncio.sleep(delay)

        try:
            await self._cleanup()
            self._session = aiohttp.ClientSession(trust_env=True)
            await self._connect_ws()
            return 0  # 重连成功，重置退避
        except Exception as exc:  # noqa: BLE001
            logger.warning("QQ WS 重连失败: %s", exc)
            return min(backoff_idx + 1, len(RECONNECT_BACKOFF) - 1)

    async def _read_events(self) -> None:
        """读取 WS 帧并分发"""
        if not self._ws:
            return
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                payload = json.loads(msg.data)
                self._dispatch_payload(payload)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                raise QQCloseError(0, str(self._ws.exception()))
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                code = self._ws.close_code or 0
                raise QQCloseError(code, "连接已关闭")

    # ── 事件分发 ──────────────────────────────────────────────

    def _dispatch_payload(self, payload: dict[str, Any]) -> None:
        """路由入站 WS 帧"""
        op = payload.get("op")
        s = payload.get("s")
        d = payload.get("d")

        # 更新序列号
        if isinstance(s, int) and (self._last_seq is None or s > self._last_seq):
            self._last_seq = s

        # op 10 = Hello
        if op == 10:
            d_data = d if isinstance(d, dict) else {}
            interval_ms = d_data.get("heartbeat_interval", 30000)
            self._heartbeat_interval = interval_ms / 1000.0 * 0.8
            logger.info("QQ 心跳间隔: %.1fs", self._heartbeat_interval)

            # 首次连接发 Identify，断线重连发 Resume
            if self._session_id:
                asyncio.create_task(self._send_resume())
            else:
                asyncio.create_task(self._send_identify())
            return

        # op 0 = Dispatch
        if op == 0:
            t = payload.get("t", "")
            if t == "READY":
                d_data = d if isinstance(d, dict) else {}
                self._session_id = d_data.get("session_id", "")
                logger.info("QQ READY, session_id=%s", self._session_id)
                return

            # 业务事件交给 adapter
            if d and isinstance(d, dict):
                asyncio.create_task(self._on_event(t, d))  # type: ignore[arg-type]
            return

        # op 7 = Server Reconnect
        if op == 7:
            logger.info("QQ 服务端要求重连")
            if self._ws and not self._ws.closed:
                asyncio.create_task(self._ws.close())
            return

        # op 9 = Invalid Session
        if op == 9:
            logger.warning("QQ 会话无效，清除 session 状态")
            self._session_id = ""
            self._last_seq = None
            return

        # op 11 = Heartbeat ACK（忽略）
        if op == 11:
            return

    # ── 鉴权 ──────────────────────────────────────────────────

    async def _send_identify(self) -> None:
        """发送 op 2 Identify"""
        assert self._session is not None
        token = await ensure_token(self._session, self.app_id, self.client_secret)
        payload = {
            "op": 2,
            "d": {
                "token": f"QQBot {token}",
                "intents": INTENT_DIRECT_MESSAGES | INTENT_GROUP_MESSAGES,
                "shard": [0, 1],
                "properties": {
                    "$os": "windows",
                    "$browser": "illusion-code",
                    "$device": "illusion-code",
                },
            },
        }
        await self._send_json(payload)
        logger.info("QQ Identify 已发送")

    async def _send_resume(self) -> None:
        """发送 op 6 Resume"""
        assert self._session is not None
        token = await ensure_token(self._session, self.app_id, self.client_secret)
        payload = {
            "op": 6,
            "d": {
                "token": f"QQBot {token}",
                "session_id": self._session_id,
                "seq": self._last_seq,
            },
        }
        await self._send_json(payload)
        logger.info("QQ Resume 已发送, session_id=%s", self._session_id)

    # ── 底层发送 ──────────────────────────────────────────────

    async def _send_json(self, data: dict[str, Any]) -> None:
        """发送 JSON 帧"""
        if self._ws and not self._ws.closed:
            await self._ws.send_json(data)
