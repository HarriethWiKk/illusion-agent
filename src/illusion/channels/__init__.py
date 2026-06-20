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
from typing import TYPE_CHECKING, Any

from illusion.channels.config import load_channels_config

if TYPE_CHECKING:
    from illusion.channels.base import Channel, InboundMessage
    from illusion.channels.config import ChannelsConfig
    from illusion.config.settings import Settings

logger = logging.getLogger(__name__)


def _config_fingerprint(cfg: "ChannelsConfig") -> str:
    """计算渠道配置指纹（用于检测配置变更后重启守护进程）

    Args:
        cfg: 渠道配置

    Returns:
        str: 配置指纹（MD5 hex）
    """
    import hashlib
    import json as _json

    # 只取影响守护进程行为的字段
    enabled_channels = []
    if cfg.feishu.enabled:
        enabled_channels.append(f"feishu:{cfg.feishu.app_id}")
    if cfg.weixin.enabled:
        enabled_channels.append(f"weixin:{cfg.weixin.account_id}:{cfg.weixin.token}")
    if cfg.qq.enabled:
        enabled_channels.append(f"qq:{cfg.qq.app_id}:{cfg.qq.client_secret}")
    raw = _json.dumps(sorted(enabled_channels), ensure_ascii=False)
    return hashlib.md5(raw.encode()).hexdigest()


def maybe_spawn_channel_daemon() -> None:
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
        return  # 无启用渠道，静默跳过

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
            return  # 配置未变，跳过

        # 配置已变，终止旧守护进程后重启（is_running 已确认存活）
        from illusion.channels.pid import read_pid
        old_pid = read_pid(pid_file.path)
        if old_pid is not None:
            try:
                if os.name == "nt":
                    import ctypes
                    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
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
    try:
        log_file = open(log_path, "ab")  # noqa: SIM115  追加写，子进程持有句柄
        # 继承当前环境并强制 UTF-8 编码，避免 Windows GBK 遇到 emoji 崩溃
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.Popen(
            [sys.executable, "-m", "illusion", "channel", "serve"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creation_flags,
            close_fds=True,
            env=env,
        )
        pid_file.acquire(proc.pid)
        fingerprint_path.write_text(current_fp, encoding="utf-8")
        return proc
    except OSError as exc:
        logger.warning("启动渠道守护进程失败: %s", exc)
        return None


class ChannelRunner:
    """渠道消息接入 agent 的运行器

    监听渠道入站消息，为每条消息构建临时 runtime 跑 agent，
    流式回复到渠道，并维护渠道会话历史。

    Attributes:
        channel: 渠道实例
        settings: 主设置
        session_store: 飞书会话存储
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
        # 按渠道类型构造会话存储（当前仅飞书）
        from illusion.channels.feishu.session_map import FeishuSessionStore
        self.session_store = FeishuSessionStore(
            data_dir=session_data_dir,
            group_sessions_per_user=group_sessions_per_user,
        )
        self._feishu_config = feishu_config  # 飞书配置（构造工具用）
        self._pending_replies: dict[str, asyncio.Future[str]] = {}  # 权限/询问待回复
        self._stop = False

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
    def _log_task_exception(task: asyncio.Task) -> None:
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

        Args:
            msg: 入站消息
        """
        # 检查 /delete 信号：先执行 /new（清所有会话+发确认），再处理消息
        if self.session_store.check_signal():
            for path in self.session_store.data_dir.glob("*.json"):
                try:
                    path.unlink()
                except OSError:
                    pass
            from illusion.config.i18n import t as _t
            from illusion.channels.qq.adapter import QQChannel as _QQChannel
            if isinstance(self.channel, _get_weixin_channel_class()):
                await self.channel.send_text(msg.chat_id, _t("weixin_cmd_new"))
            elif isinstance(self.channel, _QQChannel):
                await self.channel.send_text(msg.chat_id, _t("qq_cmd_new"))
            else:
                await self.channel.send_text(msg.chat_id, _t("feishu_cmd_new"))
            self.session_store.clear_signal()

        # 1. 待回复的权限/询问
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
        try:
            await self._run_agent(msg)
        except Exception as exc:  # noqa: BLE001
            logger.exception("处理渠道消息异常: %s", exc)
            try:
                await self.channel.send_text(msg.chat_id, f"❌ 处理失败: {str(exc)[:100]}")
            except Exception:  # noqa: BLE001
                pass

    def _get_command_handler(self) -> Any:
        """按渠道类型返回对应的斜杠命令处理器

        Returns:
            BaseCommandHandler 实例或 None（未知渠道）
        """
        from illusion.channels.feishu.adapter import FeishuChannel
        from illusion.channels.feishu.commands import FeishuCommandHandler
        if isinstance(self.channel, FeishuChannel):
            return FeishuCommandHandler(self.channel, self.session_store)
        try:
            from illusion.channels.weixin.adapter import WeixinChannel
            from illusion.channels.weixin.commands import WeixinCommandHandler
            if isinstance(self.channel, WeixinChannel):
                return WeixinCommandHandler(self.channel, self.session_store)
        except ImportError:
            pass  # 微信模块不可用时跳过
        try:
            from illusion.channels.qq.adapter import QQChannel
            from illusion.channels.qq.commands import QQCommandHandler
            if isinstance(self.channel, QQChannel):
                return QQCommandHandler(self.channel, self.session_store)
        except ImportError:
            pass  # QQ 模块不可用时跳过
        return None

    def _build_channel_tools(self) -> list[Any]:
        """构造渠道内置工具列表（飞书文档/云盘等）

        Returns:
            list: BaseTool 实例列表，渠道配置缺失时返回空列表
        """
        if self._feishu_config is None:
            return []
        try:
            from illusion.channels.tools.feishu_doc import FeishuDocReadTool, FeishuDocCreateTool
            from illusion.channels.tools.feishu_drive import (
                FeishuDriveListTool, FeishuDriveUploadTool, FeishuDriveDownloadTool,
            )
            return [
                FeishuDocReadTool(self._feishu_config),
                FeishuDocCreateTool(self._feishu_config),
                FeishuDriveListTool(self._feishu_config),
                FeishuDriveUploadTool(self._feishu_config),
                FeishuDriveDownloadTool(self._feishu_config),
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("构造飞书工具失败: %s", exc)
            return []

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

        # 检测渠道是否支持消息编辑（仅飞书支持卡片 patch）
        from illusion.channels.feishu.adapter import FeishuChannel
        supports_edit = isinstance(self.channel, FeishuChannel)

        # 统一收集流式文本，处理完后一次性发送/渲染
        collected_text: list[str] = []
        thinking_msg_id: str | None = None  # 飞书"思考中"卡片的 msg_id

        async def render_event(ev: Any) -> None:
            """流式事件收集（飞书和微信统一：仅累积文本，不实时更新）"""
            if isinstance(ev, AssistantTextDelta):
                collected_text.append(ev.text)
            elif isinstance(ev, ErrorEvent):
                collected_text.append(f"\n❌ {ev.message}")

        if supports_edit:
            # 飞书：发送"正在思考中..."卡片，处理完后一次性 patch
            from illusion.config.i18n import t as _t
            thinking_msg_id = await self.channel.send_text(
                msg.chat_id, _t("feishu_thinking"), reply_to=msg.message_id,
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
        try:
            bundle = await build_runtime(
                model=resolved_model,
                api_key=self.settings.resolve_api_key(),
                restore_messages=session.messages if session.messages else None,
                restore_session_id=session.session_id,
                is_interactive=False,
                permission_prompt=self._make_permission_prompt(msg.chat_id),
                ask_user_prompt=self._make_ask_user_prompt(msg.chat_id),
                channel_tools=self._build_channel_tools(),
            )
        except Exception as exc:
            logger.exception("构建 runtime 失败: %s", exc)
            await self.channel.send_text(msg.chat_id, f"❌ 启动失败: {str(exc)[:100]}")
            return

        try:
            await handle_line(
                bundle, msg.text,
                print_system=print_system,
                render_event=render_event,
                clear_output=clear_output,
            )
            full_text = "".join(collected_text).strip()
            logger.info("agent 处理完成，回复长度=%d", len(full_text))
            if full_text:
                if supports_edit and thinking_msg_id:
                    # 飞书：一次性 patch "思考中"卡片为完整回复
                    await self.channel.edit_message(msg.chat_id, thinking_msg_id, full_text)
                else:
                    # 微信/QQ：一次性发送（QQ 群聊需要 reply_to 定位消息）
                    await self.channel.send_text(msg.chat_id, full_text,
                                                 reply_to=msg.message_id)
            # 持久化渠道会话历史
            engine = getattr(bundle, "engine", None)
            msgs = getattr(engine, "messages", None)
            if msgs is not None and hasattr(msgs, "__iter__"):
                try:
                    self.session_store.save(session, _serialize_messages(list(msgs)))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("渠道会话持久化失败: %s", exc)
            else:
                logger.warning("无法从 bundle.engine 获取会话历史，跳过持久化")
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
        """构造用户问答回调（推到飞书等回复）"""
        async def _ask(question: str) -> str:
            await self.channel.send_text(chat_id, f"❓ {question}")
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


def _serialize_messages(messages: list[Any]) -> list[dict]:
    """把 ConversationMessage 列表序列化为 dict 列表

    Args:
        messages: ConversationMessage 列表

    Returns:
        list[dict]: 序列化后的消息
    """
    result: list[dict] = []
    for m in messages:
        if hasattr(m, "model_dump"):
            result.append(m.model_dump(mode="json"))
        elif isinstance(m, dict):
            result.append(m)
    return result
