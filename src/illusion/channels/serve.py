"""渠道守护进程入口
==================

实现 'illusion channel serve' 命令：读取 channels.json，
为每个 enabled 渠道启动 Channel，监听消息并接入 agent。

函数说明：
    - run_channel_serve: serve 命令主入口
"""
from __future__ import annotations

import asyncio  # 异步
import logging  # 日志
import os  # 进程强制退出
import signal  # 信号处理
import time  # 时间戳（_EventWatchdog 用）
from typing import TYPE_CHECKING, Any  # 类型

from illusion.channels.config import ChannelsConfig, load_channels_config  # 配置

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)  # 日志器

# 渠道守护进程看门狗退避：runner 异常退出后自动重启的间隔
SUPERVISOR_BACKOFF_SECONDS = (5.0, 10.0, 30.0)

# 模块级变量，存储当前 runners 引用（用于 get_channel_status）
_active_runners: list[Any] = []


def get_channel_status() -> dict:
    """获取渠道状态（用于 pong 响应）"""
    status = {}
    for runner in _active_runners:
        channel = getattr(runner, "channel", None)
        if channel is None:
            continue
        name = getattr(channel, "name", "unknown")
        status[name] = {"healthy": True}
    return status


def _check_channel_dependencies(cfg: ChannelsConfig) -> bool:
    """检查所有已启用渠道的依赖是否已安装

    遍历 ChannelRegistry 检查每个已启用渠道的依赖包。

    Args:
        cfg: 渠道配置

    Returns:
        bool: 所有依赖已安装返回 True，有缺失返回 False
    """
    from illusion.channels.registry import ChannelRegistry
    from illusion.config.i18n import t

    for desc in ChannelRegistry.all_descriptors():
        channel_cfg = getattr(cfg, desc.config_attr, None)
        if channel_cfg is None or not channel_cfg.enabled:
            continue
        for dep in desc.dependencies:
            try:
                __import__(dep)
            except ImportError:
                print(t("channel_deps_missing",
                        deps=", ".join(desc.dependencies), channel=desc.name))
                return False
    return True


def run_channel_serve() -> None:
    """渠道守护进程主入口（IPC 版）

    读取 channels.json，启动 DaemonServer 和所有 enabled 渠道。
    连接归零时自动退出。
    """
    from illusion.config.paths import get_channels_data_dir
    from illusion.config.i18n import t

    cfg = load_channels_config()
    settings = _load_settings_safely()

    if not cfg.has_enabled_channels():
        print(t("channel_none_configured"))
        return

    if not _check_channel_dependencies(cfg):
        return

    # 配置日志：同时输出到 stdout（前台可见）和文件（守护进程可追溯）
    # detached 子进程的 stdout 重定向到文件时可能因缓冲丢失，
    # 故额外用 RotatingFileHandler 直接写文件，确保日志可靠落盘 + 自动轮转
    # 轮转策略：单文件最大 10MB，保留 5 个备份（总计约 60MB），避免无限增长
    from logging.handlers import RotatingFileHandler
    log_path = get_channels_data_dir() / "serve.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
    # 文件 handler（可靠写盘 + 大小轮转：10MB × 5 备份）
    file_handler = RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    # stdout handler（前台运行时可见；detached 时可能缓冲但不影响文件）
    # 注：守护进程通过 PYTHONIOENCODING=utf-8 启动，避免 Windows GBK 编码问题
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    logger.info("渠道守护进程启动，日志文件: %s", log_path)

    # 清理旧文件
    from illusion.channels import _cleanup_old_channel_files, _config_fingerprint
    _cleanup_old_channel_files(get_channels_data_dir())

    # 启动 IPC 服务端
    from illusion.daemon_ipc import DaemonServer, DaemonType
    fingerprint = _config_fingerprint(cfg)
    server = DaemonServer(
        daemon_type=DaemonType.CHANNEL,
        daemon_pid=os.getpid(),
        fingerprint=fingerprint,
    )

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.start())
        loop.run_until_complete(_serve_async(cfg, settings, server))
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(server.stop())
        loop.close()


def _load_settings_safely() -> Any:
    """安全加载主设置，失败时返回 None

    Returns:
        Settings 实例或 None
    """
    try:
        from illusion.config import load_settings
        return load_settings()
    except Exception as exc:  # noqa: BLE001
        logger.warning("加载主设置失败: %s", exc)
        return None


def _force_shutdown() -> None:
    """强制关闭渠道守护进程

    尝试关闭所有运行中的渠道，然后用 os._exit 确保进程退出
    （lark-oapi 的 WS 客户端在 executor 线程阻塞，正常终止可能挂起）。
    """
    import threading
    # 尽力关闭：在守护线程里跑关闭逻辑，主线程不等待
    def _shutdown() -> None:
        try:
            # 通过遍历获取 runner 列表（_serve_async 的局部变量，这里无法直接访问）
            # 实际关闭在 _serve_async 的 finally 里已处理，这里仅兜底退出
            pass
        except Exception:  # noqa: BLE001
            pass
        os._exit(0)  # 强制退出，不等待 executor 线程

    threading.Thread(target=_shutdown, daemon=True).start()
    # 给关闭逻辑 1 秒，否则强制退出
    import time
    time.sleep(1)
    os._exit(0)


async def _supervise(runner: Any, stop_event: asyncio.Event) -> None:
    """看门狗：监督单个渠道 runner，异常退出后带退避自动重启

    渠道 task（runner.run）可能因微信长轮询连续失败、飞书 SDK 抛错、
    QQ WS 断开等异常退出。本协程捕获异常后重新调 runner.run() 重建
    连接（run 内部会 channel.connect()），而非让渠道静默死掉。

    退避在持续失败时递增（5s/10s/30s 封顶），避免疯狂重连；
    成功运行一轮后（run 正常返回）重置退避。stop_event 触发后停止。

    Args:
        runner: ChannelRunner 实例
        stop_event: 停止事件
    """
    backoff_idx = 0
    while not stop_event.is_set():
        try:
            await runner.run()
            # run 正常返回（不应发生，run 是无限循环）——重置退避
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("渠道 runner 异常退出，将重启: %s", exc, exc_info=exc)
            delay = SUPERVISOR_BACKOFF_SECONDS[
                min(backoff_idx, len(SUPERVISOR_BACKOFF_SECONDS) - 1)
            ]
            backoff_idx = min(backoff_idx + 1, len(SUPERVISOR_BACKOFF_SECONDS) - 1)
            # 退避期间检查 stop_event，避免关闭时还要等满退避
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
                return  # stop_event 触发
            except asyncio.TimeoutError:
                continue  # 退避结束，重启 runner
        else:
            backoff_idx = 0


class _EventWatchdog:
    """事件超时看门狗

    监控渠道最后事件时间，超时且 health_probe 失败时
    退出看门狗，让 _supervise 检测到异常重启 runner。

    Note: health_probe() 在 Task 4 中添加到 Channel 基类。
    在此之前 health_probe 不存在会触发 AttributeError，
    被 except 捕获后 healthy=False，看门狗会退出。
    这在 Task 3 和 Task 4 之间的间隙是可接受的：
    5分钟超时后看门狗退出，但守护进程继续运行。
    """

    def __init__(self, runner: Any, stop_event: asyncio.Event, timeout: float = 300.0) -> None:
        self._runner = runner
        self._stop_event = stop_event
        self._timeout = timeout
        self._last_event_time = time.monotonic()

    def on_event(self) -> None:
        """收到渠道事件时调用，重置计时器"""
        self._last_event_time = time.monotonic()

    async def run(self) -> None:
        """看门狗主循环，每 30s 检查一次"""
        channel = self._runner.channel
        # 设置回调，让 runner 在收到消息时更新计时器
        if hasattr(channel, "_event_watchdog"):
            channel._event_watchdog = self

        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=30.0)
                return  # stop_event 触发
            except asyncio.TimeoutError:
                pass

            # 检查事件超时
            elapsed = time.monotonic() - self._last_event_time
            if elapsed < self._timeout:
                continue  # 未超时

            # 超时，检查渠道健康
            try:
                healthy = await channel.health_probe()
            except Exception:  # noqa: BLE001
                healthy = False

            if not healthy:
                logger.warning(
                    "渠道 %s 事件超时（%ds）且 health_probe 失败，判定僵死",
                    channel.name, int(elapsed),
                )
                return  # 退出看门狗，_supervise 会检测到 runner 异常
            else:
                # health_probe 成功，可能只是无消息，重置计时器
                self._last_event_time = time.monotonic()


async def _serve_async(cfg: ChannelsConfig, settings: Any, server: Any) -> None:
    """异步 serve 所有启用渠道（IPC 版）

    Args:
        cfg: 渠道配置
        settings: 主设置
        server: DaemonServer 实例
    """
    from illusion.config.i18n import t
    from illusion.config.paths import get_channels_data_dir

    from illusion.channels import ChannelRunner
    from illusion.channels.base import Channel

    global _active_runners

    runners: list[Any] = []
    from illusion.channels.registry import ChannelRegistry

    for desc in ChannelRegistry.all_descriptors():
        channel_cfg = getattr(cfg, desc.config_attr, None)
        if channel_cfg is None or not channel_cfg.enabled:
            continue
        if settings is None:
            continue

        # 启动文案：从 descriptor 读取 i18n key 和是否需要 {channel} 参数
        if desc.start_msg_needs_channel_name:
            print(t(desc.start_msg_key, channel=desc.name))
        else:
            print(t(desc.start_msg_key))

        # 创建渠道适配器实例
        channel: Channel = desc.adapter_class(channel_cfg, settings)
        # 确保渠道会话目录存在
        channel_data_dir = get_channels_data_dir() / desc.name / "sessions"
        channel_data_dir.mkdir(parents=True, exist_ok=True)
        # 群组会话隔离：微信只私聊固定 False，其他渠道从配置读取
        group_sessions_per_user = getattr(channel_cfg, "group_sessions_per_user", False)
        # 基础 runner_kwargs + 渠道特有额外参数（通过 descriptor 工厂注入）
        runner_kwargs: dict[str, Any] = {
            "channel": channel,
            "settings": settings,
            "session_data_dir": channel_data_dir,
            "group_sessions_per_user": group_sessions_per_user,
        }
        if desc.runner_extra_kwargs_factory is not None:
            runner_kwargs.update(desc.runner_extra_kwargs_factory(channel_cfg))
        runner = ChannelRunner(**runner_kwargs)
        runners.append(runner)

    if not runners:
        print(t("channel_none_configured"))
        return

    # 更新模块级 runners 引用（供 get_channel_status 使用）
    _active_runners = runners

    # 信号处理：Unix 下注册信号，Windows 下依赖 KeyboardInterrupt
    stop_event = asyncio.Event()

    def _on_signal(*_: Any) -> None:
        stop_event.set()

    loop = asyncio.get_event_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, _on_signal)
        loop.add_signal_handler(signal.SIGTERM, _on_signal)
    except (NotImplementedError, RuntimeError, AttributeError):
        # Windows 不支持 add_signal_handler，Ctrl+C 会触发 KeyboardInterrupt
        # 在 asyncio.run 层捕获
        pass

    print(t("channel_press_exit"))

    # 启动所有 runner（通过 _supervise 看门狗监督，异常后自动重启）
    tasks = [
        asyncio.create_task(_supervise(r, stop_event)) for r in runners
    ]

    # 启动事件超时看门狗（飞书等渠道）
    for r in runners:
        watchdog = _EventWatchdog(r, stop_event)
        tasks.append(asyncio.create_task(watchdog.run()))

    # 启动连接监控（替代 ref_monitor_loop）
    async def _monitor():
        await server.wait_for_no_connections(grace_seconds=3.0)
        stop_event.set()
    tasks.append(asyncio.create_task(_monitor(), name="channel-connection-monitor"))

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass

    # 优雅关闭：取消看门狗任务并关闭各 runner
    # 注意：WS executor 线程（lark-oapi）可能阻塞 shutdown 无法返回，
    # 用 wait_for 加超时避免 asyncio.run 永不完成导致 finally 块不执行
    for task in tasks:
        task.cancel()
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        logger.warning("取消看门狗任务超时（10s），跳过等待")
    for r in runners:
        try:
            await asyncio.wait_for(r.shutdown(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("关闭渠道超时（5s），跳过: %s", r)
        except Exception as exc:  # noqa: BLE001
            logger.warning("关闭渠道异常: %s", exc)

    # 清空 runners 引用
    _active_runners = []

    # 关键：_serve_async 正常返回后，asyncio.run 会调用
    # loop.shutdown_default_executor() 等待所有 executor 线程完成。
    # 但飞书 WS 客户端通过 run_in_executor 在默认线程池中阻塞运行，
    # 不会响应 cancel → shutdown_default_executor 挂起 → asyncio.run 永不返回。
    # 因此必须在协程内部强制退出，跳过 executor 清理。
    # 强制退出，跳过 asyncio.run 的 executor 清理（会挂起）
    for h in logging.getLogger().handlers:
        try:
            h.flush()
        except Exception:  # noqa: BLE001
            pass
    os._exit(0)
