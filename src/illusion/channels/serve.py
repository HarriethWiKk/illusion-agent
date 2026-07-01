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

# 渠道守护进程看门狗退避：runner 异常退出后自动重启的间隔
SUPERVISOR_BACKOFF_SECONDS = (5.0, 10.0, 30.0)


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
    """渠道守护进程主入口

    读取 channels.json，启动所有 enabled 渠道，监听消息直至收到中断信号。
    缺少渠道 SDK 依赖时打印提示并返回（不崩溃）。

    Windows 下 Ctrl+C 通过 KeyboardInterrupt 捕获，关闭后用 os._exit 确保退出
    （WS executor 线程可能无法干净终止）。
    """
    # 启动前检查：若已有守护进程在运行（PID 文件指向存活进程），则拒绝启动
    # 防止 maybe_spawn_channel_daemon 竞态条件导致两个守护进程同时运行
    # （两个进程同时 spawn 时，PID 文件写入有竞态，可能都写入成功导致孤儿）
    from illusion.config.paths import get_channels_data_dir
    from illusion.channels.pid import PidFile, read_pid

    data_dir = get_channels_data_dir()
    pid_file = PidFile(data_dir / "daemon.pid")
    if pid_file.is_running():
        existing_pid = read_pid(pid_file.path) or 0
        # 当前进程的 PID 与 PID 文件记录的不同 → 已有另一个守护进程在运行
        if existing_pid and existing_pid != os.getpid():
            print(
                f"[channel] 守护进程已在运行 (PID={existing_pid})，拒绝重复启动。"
                f" 若确信无进程在运行，请删除 {pid_file.path} 后重试。"
            )
            return

    cfg = load_channels_config()
    settings = _load_settings_safely()

    if not cfg.has_enabled_channels():
        from illusion.config.i18n import t
        print(t("channel_none_configured"))
        return

    # 检查渠道依赖（遍历 registry）
    if not _check_channel_dependencies(cfg):
        return

    # 配置日志：同时输出到 stdout（前台可见）和文件（守护进程可追溯）
    # detached 子进程的 stdout 重定向到文件时可能因缓冲丢失，
    # 故额外用 RotatingFileHandler 直接写文件，确保日志可靠落盘 + 自动轮转
    # 轮转策略：单文件最大 10MB，保留 5 个备份（总计约 60MB），避免无限增长
    from logging.handlers import RotatingFileHandler

    from illusion.config.paths import get_channels_data_dir
    log_path = get_channels_data_dir() / "serve.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
    # 文件 handler（可靠写盘 + 大小轮转：10MB × 5 备份）
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    # stdout handler（前台运行时可见；detached 时可能缓冲但不影响文件）
    # 注：守护进程通过 PYTHONIOENCODING=utf-8 启动，避免 Windows GBK 编码问题
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    logger.info("渠道守护进程启动，日志文件: %s", log_path)

    # 写入当前进程 PID 到 PID 文件（覆盖 maybe_spawn_channel_daemon 写入的 PID）
    # 确保后续 maybe_spawn_channel_daemon 检查时能正确识别当前守护进程
    try:
        pid_file.acquire(os.getpid())
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入 daemon.pid 失败: %s", exc)

    try:
        asyncio.run(_serve_async(cfg, settings))
    except KeyboardInterrupt:
        stream_handler.flush()
        file_handler.flush()
        print("\n收到中断信号，正在关闭...")
        # 关闭资源后强制退出（WS executor 线程可能阻塞 os.kill 无法终止）
        _force_shutdown()
    finally:
        # 退出时释放 PID 文件，避免 maybe_spawn_channel_daemon 误判为仍在运行
        try:
            pid_file.release()
        except Exception:  # noqa: BLE001
            pass


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


async def _serve_async(cfg: ChannelsConfig, settings: Any) -> None:
    """异步 serve 所有启用渠道

    Args:
        cfg: 渠道配置
        settings: 主设置
    """
    from illusion.config.i18n import t
    from illusion.config.paths import get_channels_data_dir

    from illusion.channels import ChannelRunner
    from illusion.channels.base import Channel

    runners: list[Any] = []  # ChannelRunner 列表
    from illusion.channels.registry import ChannelRegistry

    # 渠道启动文案的 i18n key 映射
    _start_msg_keys = {
        "feishu": "channel_starting",
        "weixin": "channel_starting_weixin",
        "qq": "channel_starting_qq",
    }

    for desc in ChannelRegistry.all_descriptors():
        channel_cfg = getattr(cfg, desc.config_attr, None)
        if channel_cfg is None or not channel_cfg.enabled:
            continue
        if settings is None:
            continue

        # 启动文案（feishu 用 channel 参数，weixin/qq 用独立 key）
        msg_key = _start_msg_keys.get(desc.name, "channel_starting")
        if desc.name == "feishu":
            print(t(msg_key, channel=desc.name))
        else:
            print(t(msg_key))

        # 创建渠道适配器实例
        channel: Channel = desc.adapter_class(channel_cfg, settings)
        # 确保渠道会话目录存在
        channel_data_dir = get_channels_data_dir() / desc.name / "sessions"
        channel_data_dir.mkdir(parents=True, exist_ok=True)
        # 群组会话隔离：微信只私聊固定 False，其他渠道从配置读取
        group_sessions_per_user = getattr(channel_cfg, "group_sessions_per_user", False)
        # 飞书需要额外的 feishu_config 参数
        runner_kwargs: dict[str, Any] = {
            "channel": channel,
            "settings": settings,
            "session_data_dir": channel_data_dir,
            "group_sessions_per_user": group_sessions_per_user,
        }
        if desc.name == "feishu":
            runner_kwargs["feishu_config"] = channel_cfg
        runner = ChannelRunner(**runner_kwargs)
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

    # 启动所有 runner（通过 _supervise 看门狗监督，异常后自动重启）
    tasks = [
        asyncio.create_task(_supervise(r, stop_event)) for r in runners
    ]
    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass

    # 优雅关闭：取消看门狗任务并关闭各 runner
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    for r in runners:
        try:
            await r.shutdown()
        except Exception as exc:  # noqa: BLE001
            logger.warning("关闭渠道异常: %s", exc)
