"""消息渠道模块
================

提供 IllusionCode 的消息渠道能力（飞书等）。

主要导出：
    - ChannelRunner: 渠道消息接入 agent 的运行器
    - maybe_spawn_channel_daemon: 主程序自动激活渠道守护进程

本模块仅做延迟导入，不顶层依赖任何渠道 SDK。
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from illusion.channels.config import load_channels_config
from illusion.utils.atomic_write import atomic_write_text
from illusion.utils.ref_count import add_ref

if TYPE_CHECKING:
    from illusion.channels.base import Channel, InboundMessage
    from illusion.channels.config import ChannelsConfig
    from illusion.channels.feishu.streaming import FeishuStreamingCardController
    from illusion.channels.qq.streaming import QQStreamingController
    from illusion.config.settings import Settings

logger = logging.getLogger(__name__)


def _config_fingerprint(cfg: "ChannelsConfig") -> str:
    """计算渠道配置指纹（用于检测配置变更后重启守护进程）

    遍历 ChannelRegistry，对每个已启用渠道调用其 fingerprint_factory 生成标识。

    Args:
        cfg: 渠道配置

    Returns:
        str: 配置指纹（MD5 hex）
    """
    import hashlib
    import json as _json

    from illusion.channels.registry import ChannelRegistry

    # 遍历 registry 调用各渠道的 fingerprint_factory
    enabled_channels = []
    for desc in ChannelRegistry.all_descriptors():
        channel_cfg = getattr(cfg, desc.config_attr, None)
        if channel_cfg is not None and channel_cfg.enabled:
            enabled_channels.append(desc.fingerprint_factory(channel_cfg))
    raw = _json.dumps(sorted(enabled_channels), ensure_ascii=False)
    return hashlib.md5(raw.encode()).hexdigest()


def maybe_spawn_channel_daemon() -> subprocess.Popen[bytes] | None:
    """主程序启动时自动拉起渠道守护进程

    读取 channels.json，若有 enabled 渠道且守护进程未运行，
    spawn 一个 'illusion channel serve' 子进程。

    配置变更时自动重启旧守护进程（如 channel login 新增渠道后）。

    子进程独立存活，REPL 退出后不杀。完全静默，不向主终端打印任何提示。
    """
    from illusion.config.paths import get_channels_data_dir
    from illusion.channels.pid import PidFile

    cfg = load_channels_config()
    if not cfg.has_enabled_channels():
        return None  # 无启用渠道，静默跳过

    data_dir = get_channels_data_dir()
    pid_file = PidFile(data_dir / "daemon.pid")
    fingerprint_path = data_dir / "daemon.fingerprint"
    current_fp = _config_fingerprint(cfg)

    if pid_file.is_running():
        # 守护进程在运行，检查配置是否变更
        stored_fp = ""
        try:
            stored_fp = fingerprint_path.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, OSError):
            pass
        if stored_fp == current_fp:
            # 配置未变，跳过 spawn，但追加引用
            add_ref(data_dir / "daemon.refs", os.getpid())
            return None

        # 配置已变，终止旧守护进程后重启（is_running 已确认存活）
        from illusion.channels.pid import read_pid
        old_pid = read_pid(pid_file.path)
        if old_pid is not None:
            try:
                if os.name == "nt":
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(0x00010000, False, old_pid)  # PROCESS_TERMINATE
                    if handle:
                        kernel32.TerminateProcess(handle, 0)
                        kernel32.CloseHandle(handle)
                else:
                    import signal
                    os.kill(old_pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
            pid_file.release()

    # spawn 子进程，stdout/stderr 重定向到日志文件（便于排查，不干扰主终端）
    creation_flags = 0
    if os.name == "nt":
        # Windows: DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        creation_flags = 0x00000008 | 0x00000200

    log_path = data_dir / "serve.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # daemon 的 cwd：优先用主进程 cwd，失效时回退到 data_dir，避免
    # build_runtime → load_plugins → get_project_plugins_dir 的 mkdir 因
    # cwd 无效抛 WinError 267（如主进程从临时目录启动后被清理）。
    try:
        daemon_cwd = str(Path.cwd())
    except (OSError, FileNotFoundError):
        daemon_cwd = str(data_dir)
    try:
        log_file = open(log_path, "ab")  # noqa: SIM115  追加写，子进程持有句柄
        # 继承当前环境并强制 UTF-8 编码，避免 Windows GBK 遇到 emoji 崩溃
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.Popen[Any](
            [sys.executable, "-m", "illusion", "channel", "serve"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creation_flags,
            close_fds=True,
            env=env,
            cwd=daemon_cwd,
        )
        pid_file.acquire(proc.pid)
        atomic_write_text(fingerprint_path, current_fp)
        add_ref(data_dir / "daemon.refs", os.getpid())
        return proc
    except OSError as exc:
        logger.warning("启动渠道守护进程失败: %s", exc)
        return None


def kill_channel_daemon(proc: "subprocess.Popen[bytes] | None") -> None:
    """已废弃的渠道守护进程终止函数（noop）

    .. deprecated::
        此函数为向后兼容保留。新方案采用引用计数：
        主程序退出时调用 remove_ref，守护进程自监控 refs 为空时自动退出。
        不再需要主动 kill 守护进程。

    Args:
        proc: 已废弃，忽略不处理
    """
    import warnings
    warnings.warn(
        "kill_channel_daemon() 已废弃，请使用 remove_ref + 引用计数机制",
        DeprecationWarning,
        stacklevel=2,
    )
    return


def is_channel_daemon_running() -> bool:
    """检查渠道守护进程是否正在运行（通过 PID 文件，不依赖 proc 引用）

    用于退出时判断是否需要询问用户是否一同退出渠道。

    Note:
        新方案采用引用计数后，此函数仅用于诊断/查询。
        退出处理已改为 remove_ref + 自监控，不再依赖此函数。

    Returns:
        bool: 守护进程在运行返回 True
    """
    from illusion.config.paths import get_channels_data_dir
    from illusion.channels.pid import PidFile
    pid_file = PidFile(get_channels_data_dir() / "daemon.pid")
    return pid_file.is_running()


def stop_channel_daemon_by_pid() -> bool:
    """已废弃的渠道守护进程停止函数（noop）

    .. deprecated::
        此函数为向后兼容保留。新方案采用引用计数：
        守护进程通过自监控 refs 为空时自动退出，
        不再需要通过 PID 主动停止。

    Returns:
        bool: 始终返回 False
    """
    import warnings
    warnings.warn(
        "stop_channel_daemon_by_pid() 已废弃，请使用 remove_ref + 引用计数机制",
        DeprecationWarning,
        stacklevel=2,
    )
    return False


class ChannelRunner:
    """渠道消息接入 agent 的运行器

    监听渠道入站消息，为每条消息构建临时 runtime 跑 agent，
    流式回复到渠道，并维护渠道会话历史。

    Attributes:
        channel: 渠道实例
        settings: 主设置
        session_store: 渠道会话存储（按渠道类型自动创建）
    """

    def __init__(self, *, channel: "Channel", settings: "Settings",
                 session_data_dir: Path, group_sessions_per_user: bool = True,
                 feishu_config: Any = None) -> None:
        """初始化

        Args:
            channel: 渠道实例
            settings: 主设置
            session_data_dir: 会话存储目录
            group_sessions_per_user: 群组会话是否按用户隔离
            feishu_config: 飞书渠道配置（用于构造飞书工具注入 agent）
        """
        self.channel = channel  # 渠道
        self.settings = settings  # 主设置
        # 按渠道类型构造对应的会话存储
        self.session_store = _create_session_store(
            channel=channel,
            data_dir=session_data_dir,
            group_sessions_per_user=group_sessions_per_user,
        )
        self._feishu_config = feishu_config  # 飞书配置（构造工具用）
        self._pending_replies: dict[str, asyncio.Future[str]] = {}  # 权限/询问待回复
        # 按 chat_id 串行化 agent turn，避免并行消息导致会话历史覆盖
        # （同一会话连发多条消息时，M2/M3 排队等 M1 完成后再跑）
        self._chat_locks: dict[str, asyncio.Lock] = {}
        # 当前正在运行的 agent task（按 chat_id 索引），供 /stop 中断
        self._active_agent_tasks: dict[str, asyncio.Task[None]] = {}
        self._stop = False

    def _get_chat_lock(self, chat_id: str) -> asyncio.Lock:
        """获取指定 chat_id 的串行化锁（懒创建）"""
        lock = self._chat_locks.get(chat_id)
        if lock is None:
            lock = asyncio.Lock()
            self._chat_locks[chat_id] = lock
        return lock

    async def run(self) -> None:
        """启动渠道，监听消息并处理"""
        await self.channel.connect()
        async for msg in self.channel.listen():
            if self._stop:
                break
            # 每条消息独立处理，加异常日志回调避免静默失败
            task = asyncio.create_task(self._handle_message(msg))
            task.add_done_callback(self._log_task_exception)

    @staticmethod
    def _log_task_exception(task: asyncio.Task[None]) -> None:
        """任务完成后记录未捕获异常（避免静默吞掉错误）"""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.exception("处理渠道消息未捕获异常: %s", exc, exc_info=exc)

    async def shutdown(self) -> None:
        """关闭渠道"""
        self._stop = True
        await self.channel.shutdown()

    async def _handle_message(self, msg: "InboundMessage") -> None:
        """处理单条入站消息

        优先匹配待回复的权限/询问，其次处理斜杠命令，最后跑 agent。
        同一 chat_id 的消息通过 _chat_locks 串行化，避免并行 agent turn
        导致会话历史覆盖（M2/M3 排队等 M1 完成后再跑）。

        Args:
            msg: 入站消息
        """
        # 1. 待回复的权限/询问——不加锁，让回复立即送达
        # （agent turn 持锁等待回复时，下一条消息作为回复立即 set_result，
        #   不会因锁阻塞导致 300s 超时）
        if msg.chat_id in self._pending_replies:
            fut = self._pending_replies.pop(msg.chat_id)
            if not fut.done():
                fut.set_result(msg.text)
            return

        # /stop 命令：立即中断当前 chat_id 正在运行的 agent task，不排队等锁
        # 必须在 _chat_locks 之前处理，否则会卡在串行队列里等到 agent 完成才生效
        text = msg.text.strip()
        if text.lower() == "/stop":
            await self._handle_stop(msg)
            return

        # 2/3. 斜杠命令 + agent turn：按 chat_id 串行化
        async with self._get_chat_lock(msg.chat_id):
            # 进入锁后再次检查 pending_replies：前一个 agent turn 可能
            # 刚刚设了 future 等待回复，此时新消息应作为回复而非新 turn
            if msg.chat_id in self._pending_replies:
                fut = self._pending_replies.pop(msg.chat_id)
                if not fut.done():
                    fut.set_result(msg.text)
                return

            # 2. 斜杠命令（按渠道类型选择 handler）
            handler = self._get_command_handler()
            if handler is not None and await handler.try_handle(msg):
                return

            # 3. 跑 agent
            # 将当前 task 注册到 _active_agent_tasks，供 /stop 中断
            current_task = asyncio.current_task()
            if current_task is not None:
                self._active_agent_tasks[msg.chat_id] = current_task
            try:
                await self._run_agent(msg)
            except asyncio.CancelledError:
                # /stop 取消：agent 已中断，发提示消息
                from illusion.config.i18n import t as _t
                logger.info("agent 任务被 /stop 中断: chat_id=%s", msg.chat_id)
                try:
                    await self.channel.send_text(
                        msg.chat_id, _t("cmd_stop_done"),
                        reply_to=msg.message_id,
                    )
                except Exception:  # noqa: BLE001
                    pass
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("处理渠道消息异常: %s", exc)
                try:
                    await self.channel.send_text(msg.chat_id, f"❌ 处理失败: {str(exc)[:100]}")
                except Exception:  # noqa: BLE001
                    pass
            finally:
                # 清理 task 注册（无论正常完成、异常还是取消）
                self._active_agent_tasks.pop(msg.chat_id, None)

    def _get_command_handler(self) -> Any:
        """按渠道类型返回对应的斜杠命令处理器

        遍历 ChannelRegistry，匹配 adapter_class 后调用 command_handler_factory。

        Returns:
            BaseCommandHandler 实例或 None（未知渠道）
        """
        from illusion.channels.registry import ChannelRegistry

        for desc in ChannelRegistry.all_descriptors():
            if isinstance(self.channel, desc.adapter_class):
                return desc.command_handler_factory(self.channel, self.session_store)
        return None

    async def _handle_stop(self, msg: "InboundMessage") -> None:
        """处理 /stop 命令：中断当前 chat_id 正在运行的 agent 任务

        不加 _chat_locks 锁，立即取消正在运行的 agent task。
        如果没有正在运行的任务，回复提示"无正在执行的任务"。

        Args:
            msg: /stop 命令消息
        """
        from illusion.config.i18n import t as _t

        task = self._active_agent_tasks.get(msg.chat_id)
        if task is None or task.done():
            # 无正在运行的任务
            await self.channel.send_text(
                msg.chat_id, _t("cmd_stop_no_task"),
                reply_to=msg.message_id,
            )
            return

        # 取消任务：触发 CancelledError，_run_agent 的 except 块清理流式控制器
        # _handle_message 的 except CancelledError 块发送"已中断"提示
        task.cancel()
        logger.info("/stop 已取消 agent 任务: chat_id=%s", msg.chat_id)

    def _build_channel_tools(self, msg: "InboundMessage") -> list[Any]:
        """构造渠道内置工具列表

        按渠道类型和 enabled 状态构造工具。
        媒体工具对所有已启用渠道构造（飞书/QQ/微信均支持媒体收发）。

        Args:
            msg: 入站消息（用于获取 chat_id 和 attachments）

        Returns:
            list[Any]: BaseTool 实例列表
        """
        tools: list[Any] = []

        # 媒体工具（所有渠道）
        try:
            from illusion.channels.tools.media import SendMediaTool, ReceiveMediaTool
            tools.append(SendMediaTool(
                self.channel, msg.chat_id, message_id=msg.message_id
            ))
            if msg.attachments:
                tools.append(ReceiveMediaTool(
                    self.channel, msg.chat_id, msg.attachments
                ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("构造媒体工具失败: %s", exc)

        # 飞书文档/云盘工具
        if self._feishu_config is not None:
            try:
                from illusion.channels.tools.feishu_doc import (
                    FeishuDocReadTool, FeishuDocCreateTool,
                    FeishuDocWriteTool, FeishuDocDeleteTool,
                )
                from illusion.channels.tools.feishu_drive import (
                    FeishuDriveListTool, FeishuDriveUploadTool,
                    FeishuDriveDownloadTool, FeishuDriveMkdirTool,
                    FeishuDriveDeleteTool,
                )
                tools.extend([
                    FeishuDocReadTool(self._feishu_config),
                    FeishuDocCreateTool(self._feishu_config),
                    FeishuDocWriteTool(self._feishu_config),
                    FeishuDocDeleteTool(self._feishu_config),
                    FeishuDriveListTool(self._feishu_config),
                    FeishuDriveUploadTool(self._feishu_config),
                    FeishuDriveDownloadTool(self._feishu_config),
                    FeishuDriveMkdirTool(self._feishu_config),
                    FeishuDriveDeleteTool(self._feishu_config),
                ])
            except Exception as exc:  # noqa: BLE001
                logger.warning("构造飞书工具失败: %s", exc)

        # 跨渠道文件传输工具（所有渠道）
        try:
            from illusion.channels.config import load_channels_config
            from illusion.channels.tools.cross_channel import (
                ListChannelSessionsTool,
                SendToChannelTool,
            )
            all_cfg = load_channels_config()
            # 仅当有其他 enabled 渠道时才注入（避免单渠道时 LLM 误用）
            other_enabled = [
                n for n in all_cfg.enabled_channel_names()
                if n != self.channel.name
            ]
            if other_enabled:
                tools.append(ListChannelSessionsTool(all_cfg))
                tools.append(SendToChannelTool(all_cfg))
        except Exception as exc:  # noqa: BLE001
            logger.warning("构造跨渠道工具失败: %s", exc)

        # Cron 工具（注入 origin 信息用于投递）
        try:
            from illusion.tools.cron_tool import CronTool
            tools.append(CronTool(
                origin_channel=self.channel.name,
                chat_id=msg.chat_id,
            ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("构造 Cron 工具失败: %s", exc)

        return tools

    async def _run_agent(self, msg: "InboundMessage") -> None:
        """为单条消息构建 runtime 并跑 agent

        统一流程：发送"思考中"提示 → 收集流式文本 → 一次性渲染/发送。
        飞书通过 edit_message patch 卡片，微信通过 send_text 发送。

        Args:
            msg: 入站消息
        """
        from illusion.engine.stream_events import (
            AssistantTextDelta, ErrorEvent,
        )
        from illusion.ui.runtime import build_runtime, handle_line, close_runtime

        key = self.session_store.build_session_key(msg)
        session = self.session_store.get_or_create(key, msg.user_id, msg.chat_type)

        # 提前落盘会话索引（仅当文件尚不存在时）：确保 session_id 落盘，
        # 这样进程崩溃后下次启动 get_or_create 能命中该会话记录接续，
        # 而非新建会话。注意：绝不覆盖已有 messages（否则会清空历史）。
        try:
            self.session_store.ensure_indexed(session)
        except Exception as exc:  # noqa: BLE001
            logger.warning("会话索引提前落盘失败: %s", exc)

        # 检测渠道是否支持消息编辑（仅飞书支持卡片 patch）
        from illusion.channels.feishu.adapter import FeishuChannel
        from illusion.channels.qq.adapter import QQChannel
        supports_edit = isinstance(self.channel, FeishuChannel)

        # QQ C2C 流式检测：仅私聊（chat_type="dm"）支持 stream_messages API
        qq_channel = self.channel if isinstance(self.channel, QQChannel) else None
        qq_c2c_streaming = (
            qq_channel is not None
            and msg.chat_type == "dm"
            and bool(getattr(qq_channel, "_session", None))
        )

        # 统一收集流式文本，处理完后一次性发送/渲染
        collected_text: list[str] = []
        streaming_controller: FeishuStreamingCardController | None = None  # 飞书流式卡片控制器
        qq_streaming_controller: QQStreamingController | None = None  # QQ C2C 流式控制器

        async def render_event(ev: Any) -> None:
            """流式事件收集

            飞书：通过 controller 实时流式更新卡片（含 reasoning）
            QQ C2C：通过 controller 实时流式更新消息（不展示 reasoning）
            微信/QQ 群聊：仅累积文本，处理完后一次性发送
            """
            if isinstance(ev, AssistantTextDelta):
                if supports_edit and streaming_controller:
                    if ev.reasoning:
                        await streaming_controller.on_reasoning(ev.reasoning)
                    if ev.text:
                        await streaming_controller.on_text(ev.text)
                elif qq_streaming_controller and ev.text:
                    # QQ 不展示 reasoning，只流式 answer text
                    await qq_streaming_controller.on_text(ev.text)
                collected_text.append(ev.text)
            elif isinstance(ev, ErrorEvent):
                collected_text.append(f"\n❌ {ev.message}")
                if supports_edit and streaming_controller:
                    await streaming_controller.error(ev.message)
                elif qq_streaming_controller:
                    await qq_streaming_controller.abort(ev.message)

        if supports_edit:
            # 飞书：用 CardKit 流式卡片控制器替代"思考中"卡片
            from illusion.channels.feishu.streaming import FeishuStreamingCardController
            streaming_controller = FeishuStreamingCardController(
                client=cast("FeishuChannel", self.channel)._client,
                chat_id=msg.chat_id,
                reply_to=msg.message_id,
            )
            await streaming_controller.start()
        elif qq_c2c_streaming and qq_channel is not None:
            # QQ C2C：用 stream_messages API 流式（首次有文本时才启动）
            # 确保 token 已获取（通过 _get_token，重连后自动刷新）
            token = await qq_channel._get_token()
            from illusion.channels.qq.streaming import QQStreamingController
            qq_streaming_controller = QQStreamingController(
                session=qq_channel._session,
                token=token,
                openid=msg.chat_id,
                msg_id=msg.message_id,
            )

        async def print_system(text: str) -> None:
            """系统消息转发到渠道"""
            await self.channel.send_text(msg.chat_id, text)

        async def clear_output() -> None:
            """无需清屏，空操作"""
            pass

        # 处理前：启动打字状态（微信需要，飞书空操作）
        await self.channel.start_typing(msg.chat_id)
        # 处理期间每 5s 刷新打字状态
        typing_task = asyncio.create_task(self._keep_typing_alive(msg.chat_id))

        logger.info("开始处理渠道消息: chat_id=%s text=%s", msg.chat_id, msg.text[:50])

        # 构建临时 runtime（复用 build_runtime，注入渠道工具）
        # 校验 session model 是否仍与当前活跃环境兼容，避免切格式后发到旧端点
        resolved_model = None
        if session.model:
            session_env = session.model.split(".")[0] if "." in session.model else ""
            current_env = getattr(self.settings, "_active_env_key", "") or ""
            if session_env == current_env:
                resolved_model = session.model
            else:
                logger.info("session model %s 与当前环境 %s 不匹配，使用默认模型",
                            session.model, current_env)
        # 获取平台感知提示词（含当前渠道身份 + 其他 enabled 渠道概览）
        from illusion.channels.config import load_channels_config
        from illusion.prompts.channel_hints import (
            get_channel_hint,
            list_active_sessions,
        )
        all_cfg = load_channels_config()
        qq_md = getattr(self.channel.config, "markdown_support", None)
        # 枚举其他 enabled 渠道的活跃会话
        other_names = [
            n for n in all_cfg.enabled_channel_names()
            if n != self.channel.name
        ]
        active_sessions = {
            name: list_active_sessions(name, all_cfg, limit=5)
            for name in other_names
        }
        channel_hint = get_channel_hint(
            current_channel=self.channel.name,
            channels_config=all_cfg,
            qq_markdown_support=qq_md,
            active_sessions=active_sessions,
        )

        try:
            bundle = await build_runtime(
                model=resolved_model,
                api_key=self.settings.resolve_api_key(),
                restore_messages=session.messages if session.messages else None,
                restore_session_id=session.session_id,
                is_interactive=False,
                permission_prompt=self._make_permission_prompt(msg.chat_id),
                ask_user_prompt=self._make_ask_user_prompt(msg.chat_id),
                channel_hint=channel_hint,
                channel_tools=self._build_channel_tools(msg),
            )
        except Exception as exc:
            logger.exception("构建 runtime 失败: %s", exc)
            await self.channel.send_text(msg.chat_id, f"❌ 启动失败: {str(exc)[:100]}")
            return

        # 拼接附件信息到消息文本前
        prompt_text = msg.text
        if msg.attachments:
            attach_lines = []
            for att in msg.attachments:
                size_str = f"{att.size} bytes" if att.size else "unknown size"
                attach_lines.append(
                    f"[收到附件 {att.id}: {att.filename} ({att.media_type}, {size_str})]"
                )
            prompt_text = "\n".join(attach_lines) + "\n" + msg.text

        try:
            await handle_line(
                bundle, prompt_text,
                print_system=print_system,
                render_event=render_event,
                clear_output=clear_output,
            )
            full_text = "".join(collected_text).strip()
            logger.info("agent 处理完成，回复长度=%d", len(full_text))
            if supports_edit and streaming_controller:
                # 飞书：通知 controller 完成（全卡替换为终态）
                await streaming_controller.complete()
            elif qq_streaming_controller:
                # QQ C2C：发送终结分片（input_state=DONE）
                await qq_streaming_controller.complete()
                # 降级检查：如果从未成功发出分片，走一次性发送
                if qq_streaming_controller.should_fallback_to_static and full_text:
                    await self.channel.send_text(msg.chat_id, full_text,
                                                 reply_to=msg.message_id)
            elif full_text:
                # 微信/QQ 群聊：一次性发送（QQ 群聊需要 reply_to 定位消息）
                await self.channel.send_text(msg.chat_id, full_text,
                                             reply_to=msg.message_id)
            # 持久化渠道会话历史
            engine = getattr(bundle, "engine", None)
            msgs = getattr(engine, "messages", None)
            if msgs is not None and hasattr(msgs, "__iter__"):
                try:
                    # 回写 build_runtime 生成/恢复的 session_id，避免下次仍为空
                    # 导致每次都生成新会话 ID（同一对话产生多个会话记录）
                    if bundle.session_id and session.session_id != bundle.session_id:
                        session.session_id = bundle.session_id
                    self.session_store.save(session, _serialize_messages(list(msgs)))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("渠道会话持久化失败: %s", exc)
            else:
                logger.warning("无法从 bundle.engine 获取会话历史，跳过持久化")
        except asyncio.CancelledError:
            # /stop 中断：清理流式控制器后重新抛出，让上层 _handle_message 发提示
            logger.info("agent 任务被取消: chat_id=%s", msg.chat_id)
            if supports_edit and streaming_controller:
                try:
                    await streaming_controller.error("已中断")
                except Exception:  # noqa: BLE001
                    pass
            elif qq_streaming_controller:
                try:
                    await qq_streaming_controller.abort("已中断")
                except Exception:  # noqa: BLE001
                    pass
            raise
        except Exception as exc:
            logger.exception("agent 处理异常")
            if supports_edit and streaming_controller:
                # 飞书：通知 controller 错误终态
                await streaming_controller.error(str(exc))
            elif qq_streaming_controller:
                # QQ C2C：中止流式 + 降级到一次性发送错误消息
                await qq_streaming_controller.abort(str(exc))
                await self.channel.send_text(
                    msg.chat_id, f"❌ 处理失败: {exc}", reply_to=msg.message_id,
                )
            else:
                await self.channel.send_text(
                    msg.chat_id, f"❌ 处理失败: {exc}", reply_to=msg.message_id,
                )
        finally:
            typing_task.cancel()
            await self.channel.stop_typing(msg.chat_id)
            await close_runtime(bundle)

    async def _keep_typing_alive(self, chat_id: str) -> None:
        """每 5s 刷新打字状态（微信用，飞书空操作）

        Args:
            chat_id: 目标会话
        """
        while True:
            await asyncio.sleep(5)
            try:
                await self.channel.start_typing(chat_id)
            except Exception:  # noqa: BLE001
                pass  # 打字状态失败不影响主流程

    def _make_permission_prompt(self, chat_id: str) -> Any:
        """构造权限确认回调（渠道自动批准，不影响终端对话）"""
        async def _prompt(tool: str, desc: str) -> bool:
            return True  # 渠道消息自动批准所有工具权限
        return _prompt

    def _make_ask_user_prompt(self, chat_id: str) -> Any:
        """构造用户问答回调（推到飞书等回复）

        签名与 backend_host/ws_host 的 _ask_question 一致：
        (question: str, questions: object = None) -> str

        questions 是结构化选项数据（list[dict]），含 question/header/options/
        multiSelect/noCustomInput 字段。渠道只能回复文本，故将选项 label
        附加到问题文本，让用户回复对应 label。
        """
        async def _ask(question: str, questions: object = None) -> str:
            text = f"❓ {question}"
            # 将结构化选项附加到问题文本，方便渠道用户回复
            if questions:
                try:
                    opts_lines = _format_question_options(questions)
                    if opts_lines:
                        text = f"{text}\n\n{opts_lines}"
                except Exception:  # noqa: BLE001
                    pass  # 格式化失败时只发问题文本
            await self.channel.send_text(chat_id, text)
            return await self._wait_reply(chat_id, timeout=300)
        return _ask

    async def _wait_reply(self, chat_id: str, timeout: float) -> str:
        """等待指定 chat_id 的下一条消息作为回复

        Args:
            chat_id: 会话标识
            timeout: 超时秒数

        Returns:
            str: 回复文本

        Raises:
            asyncio.TimeoutError: 超时
        """
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[str] = loop.create_future()
        self._pending_replies[chat_id] = fut
        return await asyncio.wait_for(fut, timeout=timeout)


def _format_question_options(questions: object) -> str:
    """将结构化问题选项格式化为渠道可显示的文本

    questions 结构：list[dict]，每个 dict 含：
        - question: str 子问题文本
        - header: str 标题
        - options: list[dict] 选项列表，每项含 label/description
        - multiSelect: bool 是否多选
        - noCustomInput: bool 是否禁止自定义输入

    Args:
        questions: 结构化问题数据

    Returns:
        str: 格式化后的选项文本，无选项返回空串
    """
    if not isinstance(questions, (list, tuple)):
        return ""
    lines: list[str] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        opts = q.get("options") or []
        if not opts:
            continue
        header = str(q.get("header") or "").strip()
        sub_q = str(q.get("question") or "").strip()
        if header:
            lines.append(f"【{header}】")
        if sub_q:
            lines.append(sub_q)
        for opt in opts:
            if not isinstance(opt, dict):
                continue
            label = str(opt.get("label") or "").strip()
            desc = str(opt.get("description") or "").strip()
            if label:
                lines.append(f"  • {label}" + (f" — {desc}" if desc else ""))
    return "\n".join(lines)


def _get_weixin_channel_class() -> Any:
    """延迟获取 WeixinChannel 类（避免循环导入）

    Returns:
        WeixinChannel 类，或 None（模块不可用时）
    """
    try:
        from illusion.channels.weixin.adapter import WeixinChannel
        return WeixinChannel
    except ImportError:
        return None


def _create_session_store(
    *,
    channel: "Channel",
    data_dir: Path,
    group_sessions_per_user: bool = True,
) -> Any:
    """根据渠道类型创建对应的 SessionStore

    遍历 ChannelRegistry，匹配 adapter_class 后调用 session_store_factory。
    未知渠道回退到 FeishuSessionStore（向后兼容）。

    Args:
        channel: 渠道实例
        data_dir: 会话数据目录
        group_sessions_per_user: 群组会话是否按用户隔离

    Returns:
        对应渠道的 SessionStore 实例
    """
    from illusion.channels.registry import ChannelRegistry

    for desc in ChannelRegistry.all_descriptors():
        if isinstance(channel, desc.adapter_class):
            return desc.session_store_factory(
                channel, data_dir, group_sessions_per_user
            )
    # 未知渠道回退到飞书（向后兼容）
    from illusion.channels.feishu.session_map import FeishuSessionStore
    return FeishuSessionStore(
        data_dir=data_dir,
        group_sessions_per_user=group_sessions_per_user,
    )


def _serialize_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """把 ConversationMessage 列表序列化为 dict[str, Any] 列表

    Args:
        messages: ConversationMessage 列表

    Returns:
        list[dict]: 序列化后的消息
    """
    result: list[dict[str, Any]] = []
    for m in messages:
        if hasattr(m, "model_dump"):
            result.append(m.model_dump(mode="json"))
        elif isinstance(m, dict):
            result.append(m)
    return result
