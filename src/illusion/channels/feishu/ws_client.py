"""飞书 WebSocket 客户端包装
============================

对 lark-oapi 官方 WS 客户端做轻量包装，桥接到 asyncio。

官方客户端的 start() 是同步阻塞的，本模块在 executor 线程运行它，
通过回调把原始事件投递出去，再由 adapter 线程安全地投递到 asyncio.Queue。

类说明：
    - FeishuWSClient: WS 客户端包装
"""
from __future__ import annotations

import logging  # 日志
from typing import Any, Callable  # 类型

logger = logging.getLogger(__name__)  # 日志器


class FeishuWSClient:
    """飞书官方 WS 客户端的轻量包装

    在 executor 线程运行官方客户端的阻塞 start()，
    通过回调把原始事件投递出去。

    Attributes:
        _app_id: 应用 ID
        _app_secret: 应用密钥
        _event_handler: 事件处理回调（同步，接收原始事件 dict）
        _domain: 域名 URL
        _client: 官方客户端实例（start 后赋值）
    """

    def __init__(self, *, app_id: str, app_secret: str,
                 event_handler: Callable[[dict], None], domain: str) -> None:
        """初始化

        Args:
            app_id: 应用 ID
            app_secret: 应用密钥
            event_handler: 原始事件处理回调
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
        import lark_oapi as lark  # 延迟导入
        from lark_oapi.ws.client import Client as WsClient  # type: ignore[import-not-found]

        event_handler = self._event_handler

        # 构造事件分发器：注册 im.message.receive_v1（消息接收）事件
        # 注意：register_p2_im_message_receive_v1 的回调是单参数 (event)，不是双参数
        dispatcher = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(
            lambda event: event_handler(_to_dict(event))
        ).build()

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
        """停止 WS 客户端"""
        self._running = False
        if self._client is not None:
            try:
                self._client.stop()
            except Exception as exc:  # noqa: BLE001
                logger.warning("停止飞书 WS 客户端异常: %s", exc)


def _to_dict(obj: Any) -> dict:
    """把 lark 事件对象转为 dict

    Args:
        obj: lark 事件对象

    Returns:
        dict: 事件字典
    """
    if isinstance(obj, dict):
        return obj
    # 尝试 pydantic/dict 序列化
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return {"raw": str(obj)}
