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

    asyncio.run(_serve_async(cfg, settings))


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

    # 信号处理：优雅退出
    stop_event = asyncio.Event()

    def _on_signal(*_: Any) -> None:
        stop_event.set()

    loop = asyncio.get_event_loop()
    try:
        if signal.SIGINT is not None:
            loop.add_signal_handler(signal.SIGINT, _on_signal)
            loop.add_signal_handler(signal.SIGTERM, _on_signal)
    except (NotImplementedError, RuntimeError, AttributeError):
        pass  # Windows 下信号处理有限，依赖 KeyboardInterrupt

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
