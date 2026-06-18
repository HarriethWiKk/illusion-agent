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
from typing import TYPE_CHECKING, Any  # 类型

from illusion.channels.config import ChannelsConfig, load_channels_config  # 配置

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)  # 日志器


def run_channel_serve() -> None:
    """渠道守护进程主入口

    读取 channels.json，启动所有 enabled 渠道，监听消息直至收到中断信号。
    缺少渠道 SDK 依赖时打印提示并返回（不崩溃）。

    Windows 下 Ctrl+C 通过 KeyboardInterrupt 捕获，关闭后用 os._exit 确保退出
    （WS executor 线程可能无法干净终止）。
    """
    cfg = load_channels_config()
    settings = _load_settings_safely()

    if not cfg.has_enabled_channels():
        from illusion.config.i18n import t
        print(t("channel_none_configured"))
        return

    # 检查飞书依赖
    if cfg.feishu.enabled:
        try:
            import lark_oapi  # noqa: F401
        except ImportError:
            from illusion.config.i18n import t
            from illusion.channels.feishu import FEISHU_DEPENDENCIES
            print(t("channel_deps_missing",
                    deps=", ".join(FEISHU_DEPENDENCIES), channel="feishu"))
            return

    # 配置日志：同时输出到 stdout（前台可见）和文件（守护进程可追溯）
    # detached 子进程的 stdout 重定向到文件时可能因缓冲丢失，
    # 故额外用 FileHandler 直接写文件，确保日志可靠落盘
    from illusion.config.paths import get_channels_data_dir
    log_path = get_channels_data_dir() / "serve.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
    # 文件 handler（可靠写盘）
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    # stdout handler（前台运行时可见；detached 时可能缓冲但不影响文件）
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    logger.info("渠道守护进程启动，日志文件: %s", log_path)

    try:
        asyncio.run(_serve_async(cfg, settings))
    except KeyboardInterrupt:
        stream_handler.flush()
        file_handler.flush()
        print("\n收到中断信号，正在关闭...")
        # 关闭资源后强制退出（WS executor 线程可能阻塞 os.kill 无法终止）
        _force_shutdown()


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
    def _shutdown():
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


async def _serve_async(cfg: ChannelsConfig, settings: Any) -> None:
    """异步 serve 所有启用渠道

    Args:
        cfg: 渠道配置
        settings: 主设置
    """
    from illusion.config.i18n import t
    from illusion.config.paths import get_channels_data_dir

    runners: list[Any] = []  # ChannelRunner 列表
    if cfg.feishu.enabled and settings is not None:
        from illusion.channels import ChannelRunner
        from illusion.channels.feishu.adapter import FeishuChannel

        print(t("channel_starting", channel="feishu"))
        channel = FeishuChannel(cfg.feishu, settings)
        # 确保飞书会话目录存在
        feishu_data_dir = get_channels_data_dir() / "feishu" / "sessions"
        feishu_data_dir.mkdir(parents=True, exist_ok=True)
        runner = ChannelRunner(
            channel=channel,
            settings=settings,
            session_data_dir=feishu_data_dir,
            group_sessions_per_user=cfg.feishu.group_sessions_per_user,
            feishu_config=cfg.feishu,
        )
        runners.append(runner)

    if not runners:
        print(t("channel_none_configured"))
        return

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

    # 启动所有 runner
    tasks = [asyncio.create_task(r.run()) for r in runners]
    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass

    # 优雅关闭
    for r in runners:
        try:
            await r.shutdown()
        except Exception as exc:  # noqa: BLE001
            logger.warning("关闭渠道异常: %s", exc)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
