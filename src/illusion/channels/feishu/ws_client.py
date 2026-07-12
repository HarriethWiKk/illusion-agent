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
import time  # 重复日志抑制
from typing import Any, Callable  # 类型

logger = logging.getLogger(__name__)  # 日志器


class _DuplicateLogFilter(logging.Filter):
    """重复日志抑制 filter

    参照 hermes-agent _write_runtime_status_safe 的日志降级思路：
    相同消息在 THROTTLE_SECONDS 内只放行一次，之后直接丢弃（return False）。
    避免 lark SDK 循环错误（attached to a different loop / Event loop is closed）
    爆炸式填充 log 文件造成资源浪费。

    注意：必须 return False 丢弃重复 record，而非降级 level。
    Lark logger 自带 StreamHandler(stdout) level=NOTSET(0)，降级到 DEBUG
    仍会通过 `10 >= 0` 检查输出到 stdout。守护进程 detached 时 stdout 重定向
    到文件（不受 RotatingFileHandler 管理），仍会爆炸。
    """

    THROTTLE_SECONDS = 60.0  # 同类消息抑制窗口
    _MAX_SEEN = 200  # _seen 字典上限，超出后清理过期条目

    def __init__(self) -> None:
        super().__init__()
        self._seen: dict[str, float] = {}  # key: 简化消息 → 首次时间戳

    def filter(self, record: logging.LogRecord) -> bool:
        # 只抑制 WARNING 及以上（INFO/DEBUG 原样放行）
        if record.levelno < logging.WARNING:
            return True
        # 用 record.msg（原始模板）而非 record.getMessage() 避免 format 两次
        # （handler 后续会调 getMessage() 格式化，filter 这里只需 key）
        msg = record.msg if isinstance(record.msg, str) else str(record.msg)
        # 提取前 80 字符作为 key（足够区分错误类型，忽略 conn_id 差异）
        key = msg[:80]
        now = time.monotonic()
        last_seen = self._seen.get(key)
        if last_seen is None or (now - last_seen) > self.THROTTLE_SECONDS:
            # 首次或窗口外，记录时间戳，放行
            self._seen[key] = now
            # 字典上限清理：超出时删除过期条目，避免无界增长
            if len(self._seen) > self._MAX_SEEN:
                cutoff = now - self.THROTTLE_SECONDS * 2
                self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
            return True
        # 窗口内重复，直接丢弃（return False 让所有 handler 看不到此 record）
        return False


# 模块级 filter 实例（飞书 WS 客户端导入时安装到 lark logger）
_duplicate_filter = _DuplicateLogFilter()


def _install_lark_log_filter() -> None:
    """给 lark SDK logger 安装重复日志抑制 filter

    在 start() 首次调用前安装，避免 lark SDK 循环错误爆炸填充 log 文件。
    幂等：重复调用只安装一次。
    """
    try:
        import lark_oapi.core.log as lark_log_module
        lark_logger = getattr(lark_log_module, "logger", None)
        if lark_logger is None:
            return
        # 检查是否已安装（幂等）
        if not any(isinstance(f, _DuplicateLogFilter) for f in lark_logger.filters):
            lark_logger.addFilter(_duplicate_filter)
    except Exception as exc:  # noqa: BLE001
        # 不静默：至少 debug 记录，避免 lark SDK 重命名属性后 filter 静默不安装
        logger.debug("安装 lark 日志 filter 失败: %s", exc)


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
        _lark_loop: lark SDK 独立事件循环（start 创建，stop 用它跨线程中断）

    参照 hermes-agent 的 _run_official_feishu_ws_client + disconnect 模式：
    - start() 创建独立 loop，替换 lark SDK 模块级 loop，保存到 self._lark_loop；
      finally 块清理 pending tasks + stop + close loop
    - stop() 通过 call_soon_threadsafe 取消 tasks + loop.stop() 让阻塞的 start() 返回
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
        self._lark_loop: Any = None  # lark SDK 独立事件循环（供 stop() 跨线程中断）

    def start(self) -> None:
        """启动 WS 客户端（阻塞，应在 executor 线程调用）

        构造官方 lark WS 客户端并 start()。事件通过 _event_handler 回调投递。

        关键：lark SDK 在模块加载时缓存了 asyncio.get_event_loop() 作为模块级
        变量 loop。WsClient.__init__ 创建 ExpiringCache 时调用 loop.create_task()，
        start() 内部用 loop.run_until_complete(_select()) 阻塞运行。
        守护进程主事件循环已 running，lark SDK 若复用主 loop 会抛
        RuntimeError: This event loop is already running。

        参照 hermes-agent _run_official_feishu_ws_client 模式：
        - 创建独立 loop 并替换 lark SDK 模块级 loop 变量（WsClient.__init__ 需要）
        - 保存 loop 到 self._lark_loop 供 stop() 跨线程中断
        - start() 阻塞运行，由 stop() 通过 loop.stop() 中断
        - finally 块清理 pending tasks + stop + close loop
        """
        import lark_oapi as lark  # 延迟导入
        from lark_oapi.ws.client import Client as WsClient
        import lark_oapi.ws.client as lark_ws_module  # 替换模块级 loop

        # 安装日志抑制 filter（幂等），避免 lark SDK 循环错误爆炸填充 log 文件
        _install_lark_log_filter()

        # 每次启动前创建新 loop 并替换 lark SDK 模块级 loop
        # 必须在 WsClient.__init__ 之前执行（ExpiringCache 用 loop.create_task）
        lark_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(lark_loop)
        lark_ws_module.loop = lark_loop
        self._lark_loop = lark_loop  # 供 stop() 跨线程中断

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
            # 阻塞运行（在 lark_loop 上，由 stop() 的 loop.stop() 中断 _select()）
            self._client.start()
        except Exception:
            logger.debug("飞书 WS start() 异常退出", exc_info=True)
        finally:
            # 清理 pending tasks + stop + close loop（参照 hermes-agent）
            self._running = False
            self._cleanup_loop(lark_loop)
            self._lark_loop = None

    @staticmethod
    def _cleanup_loop(loop: asyncio.AbstractEventLoop) -> None:
        """清理事件循环上的 pending tasks 并关闭 loop

        参照 hermes-agent _run_official_feishu_ws_client 的 finally 块。
        """
        try:
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        except Exception:
            pass
        try:
            loop.stop()
        except Exception:
            pass
        try:
            loop.close()
        except Exception:
            pass

    def stop(self) -> None:
        """停止 WS 客户端（线程安全，非阻塞）

        参照 hermes-agent disconnect() 模式：
        通过 call_soon_threadsafe 在 lark_loop 上调度 cancel_all_tasks，
        取消所有 pending tasks 并 call_later(0.1, loop.stop) 让阻塞的
        run_until_complete(_select()) 返回，从而让 start() 退出并执行 finally 清理。

        调用方应随后 await executor future（adapter.shutdown 负责等待线程退出）。
        """
        self._running = False
        lark_loop = self._lark_loop
        if lark_loop is None or lark_loop.is_closed():
            # start() 未调用或已退出
            return

        def cancel_all_tasks() -> None:
            """在 lark_loop 线程中取消所有 pending tasks 并停止 loop"""
            try:
                tasks = [t for t in asyncio.all_tasks(lark_loop) if not t.done()]
                for task in tasks:
                    task.cancel()
                # 延迟 0.1s 停止 loop，给 task cancellation 一个传播窗口
                lark_loop.call_later(0.1, lark_loop.stop)
            except Exception:
                pass

        try:
            lark_loop.call_soon_threadsafe(cancel_all_tasks)
            logger.info("飞书 WS 客户端已请求停止")
        except RuntimeError:
            # loop 已关闭
            pass
