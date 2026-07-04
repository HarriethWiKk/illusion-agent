"""飞书 WebSocket 客户端包装
============================

对 lark-oapi 官方 WS 客户端做轻量包装，桥接到 asyncio。

官方客户端的 start() 是同步阻塞的，本模块在 executor 线程运行它，
通过回调把强类型事件对象投递出去，再由 adapter 线程安全地投递到 asyncio.Queue。

事件对象结构（lark-oapi 强类型，非 dict）:
    P2ImMessageReceiveV1:
        .event: P2ImMessageReceiveV1Data
            .sender: EventSender
                .sender_id: UserId (.open_id / .union_id / .user_id)
                .sender_type: str ("app" 表示机器人)
                .tenant_key: str
            .message: EventMessage
                .chat_id / .chat_type ("p2p"/"group") / .message_id / .content / .mentions 等

类说明：
    - FeishuWSClient: WS 客户端包装
"""
from __future__ import annotations

import asyncio  # 跨线程调度
import logging  # 日志
from typing import Any, Callable  # 类型

logger = logging.getLogger(__name__)  # 日志器


class FeishuWSClient:
    """飞书官方 WS 客户端的轻量包装

    在 executor 线程运行官方客户端的阻塞 start()，
    通过回调把强类型事件对象投递出去。

    Attributes:
        _app_id: 应用 ID
        _app_secret: 应用密钥
        _event_handler: 事件处理回调（同步，接收 P2ImMessageReceiveV1 事件对象）
        _domain: 域名 URL
        _client: 官方客户端实例（start 后赋值）
    """

    def __init__(self, *, app_id: str, app_secret: str,
                 event_handler: Callable[[Any], None], domain: str) -> None:
        """初始化

        Args:
            app_id: 应用 ID
            app_secret: 应用密钥
            event_handler: 事件处理回调（接收强类型事件对象）
            domain: 域名 URL（如 https://open.feishu.cn）
        """
        self._app_id = app_id  # 应用 ID
        self._app_secret = app_secret  # 应用密钥
        self._event_handler = event_handler  # 事件回调
        self._domain = domain  # 域名
        self._client: Any = None  # 官方客户端
        self._running = False  # 运行标志

    def start(self) -> None:
        """启动 WS 客户端（阻塞，应在 executor 线程调用）

        构造官方 lark WS 客户端并 start()。事件通过 _event_handler 回调投递。
        """
        import lark_oapi as lark  # type: ignore[import-untyped]  # 延迟导入
        from lark_oapi.ws.client import Client as WsClient  # type: ignore[import-untyped]

        event_handler = self._event_handler

        # 构造事件分发器：注册消息接收事件 + 忽略已读回执事件
        # 注意：register_p2_im_message_receive_v1 的回调是单参数 (event)，直接传强类型对象
        # message_read_v1（已读回执）注册空处理器，避免 "processor not found" 噪音日志
        dispatcher = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(lambda event: event_handler(event))
            .register_p2_im_message_message_read_v1(lambda _event: None)
            .build()
        )

        self._client = WsClient(
            app_id=self._app_id,
            app_secret=self._app_secret,
            event_handler=dispatcher,
            domain=self._domain,
        )
        self._running = True
        try:
            self._client.start()  # 阻塞运行
        finally:
            self._running = False

    def stop(self) -> None:
        """停止 WS 客户端

        lark-oapi 的 Client 没有公开的 stop() 方法，
        通过 _disconnect() 关闭 WS 连接。
        _disconnect() 是 async 方法，需在 lark-oapi 自己的事件循环中调度
        （start() 后该 loop 持续运行，被 _select() 阻塞）。
        """
        self._running = False
        if self._client is not None:
            try:
                # 获取 lark-oapi 模块级事件循环
                from lark_oapi.ws.client import loop as lark_loop
                if lark_loop.is_running():
                    # 跨线程调度 _disconnect() 到 lark loop，等待 2s
                    future = asyncio.run_coroutine_threadsafe(
                        self._client._disconnect(), lark_loop
                    )
                    future.result(timeout=2.0)
                    logger.info("飞书 WS 客户端已断开连接")
                else:
                    # lark loop 未运行（start() 未调用或已退出），直接清理
                    self._client._conn = None
                    logger.debug("lark loop 未运行，跳过 _disconnect()")
            except Exception as exc:  # noqa: BLE001
                logger.warning("停止飞书 WS 客户端异常: %s", exc)
