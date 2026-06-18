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
    from illusion.config.settings import Settings

logger = logging.getLogger(__name__)


def maybe_spawn_channel_daemon() -> None:
    """主程序启动时自动拉起渠道守护进程

    读取 channels.json，若有 enabled 渠道且守护进程未运行，
    spawn 一个 'illusion channel serve' 子进程。

    子进程独立存活，REPL 退出后不杀。完全静默，不向主终端打印任何提示。
    """
    from illusion.config.paths import get_channels_data_dir
    from illusion.channels.pid import PidFile

    cfg = load_channels_config()
    if not cfg.has_enabled_channels():
        return  # 无启用渠道，静默跳过

    pid_file = PidFile(get_channels_data_dir() / "daemon.pid")
    if pid_file.is_running():
        return  # 已在运行，静默跳过

    # spawn 子进程，stdout/stderr 重定向到日志文件（便于排查，不干扰主终端）
    creation_flags = 0
    if os.name == "nt":
        # Windows: DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        creation_flags = 0x00000008 | 0x00000200

    log_path = get_channels_data_dir() / "serve.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        log_file = open(log_path, "ab")  # noqa: SIM115  追加写，子进程持有句柄
        proc = subprocess.Popen(
            [sys.executable, "-m", "illusion", "channel", "serve"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creation_flags,
            close_fds=True,
        )
        pid_file.acquire(proc.pid)
    except OSError as exc:
        logger.warning("启动渠道守护进程失败: %s", exc)
        return


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
        # 1. 待回复的权限/询问
        if msg.chat_id in self._pending_replies:
            fut = self._pending_replies.pop(msg.chat_id)
            if not fut.done():
                fut.set_result(msg.text)
            return

        # 2. 飞书侧斜杠命令
        from illusion.channels.feishu.commands import FeishuCommandHandler
        handler = FeishuCommandHandler(self.channel, self.session_store)
        if await handler.try_handle(msg):
            return

        # 3. 跑 agent
        try:
            await self._run_agent(msg)
        except Exception as exc:  # noqa: BLE001
            logger.exception("处理飞书消息异常: %s", exc)
            try:
                await self.channel.send_text(msg.chat_id, f"❌ 处理失败: {str(exc)[:100]}")
            except Exception:  # noqa: BLE001
                pass

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

        Args:
            msg: 入站消息
        """
        from illusion.channels.feishu.stream_editor import FeishuStreamEditor
        from illusion.engine.stream_events import (
            AssistantTextDelta, ToolExecutionStarted, ErrorEvent,
        )
        from illusion.ui.runtime import build_runtime, handle_line, close_runtime

        key = self.session_store.build_session_key(msg)
        session = self.session_store.get_or_create(key, msg.user_id, msg.chat_type)

        editor = FeishuStreamEditor(self.channel, msg.chat_id, msg.message_id)

        async def render_event(ev: Any) -> None:
            """流式事件渲染到飞书"""
            if isinstance(ev, AssistantTextDelta):
                await editor.on_delta(ev.text)
            elif isinstance(ev, ToolExecutionStarted):
                await editor.on_delta(f"\n\n🔧 {ev.tool_name}...")
            elif isinstance(ev, ErrorEvent):
                await self.channel.send_text(msg.chat_id, f"❌ {ev.message}")

        async def print_system(text: str) -> None:
            """系统消息转发到飞书"""
            await self.channel.send_text(msg.chat_id, text)

        async def clear_output() -> None:
            """飞书无需清屏，空操作"""
            pass

        # 构建临时 runtime（复用 build_runtime，注入渠道工具）
        bundle = await build_runtime(
            model=session.model or None,
            api_key=self.settings.resolve_api_key(),
            restore_messages=session.messages if session.messages else None,
            restore_session_id=session.session_id,
            is_interactive=False,
            permission_prompt=self._make_permission_prompt(msg.chat_id),
            ask_user_prompt=self._make_ask_user_prompt(msg.chat_id),
            channel_tools=self._build_channel_tools(),  # 注入飞书工具
        )

        try:
            await handle_line(
                bundle, msg.text,
                print_system=print_system,
                render_event=render_event,
                clear_output=clear_output,
            )
            await editor.finalize()
            # 持久化飞书会话历史
            self.session_store.save(key, _serialize_messages(bundle.engine.messages))
        finally:
            await close_runtime(bundle)

    def _make_permission_prompt(self, chat_id: str) -> Any:
        """构造权限确认回调（推到飞书等回复）"""
        async def _prompt(tool: str, desc: str) -> bool:
            await self.channel.send_text(
                chat_id, f"⚠️ 工具 {tool} 请求权限：{desc}\n回复 'y' 批准（120s 超时自动拒绝）"
            )
            try:
                reply = await self._wait_reply(chat_id, timeout=120)
            except asyncio.TimeoutError:
                await self.channel.send_text(chat_id, "权限确认超时，已拒绝")
                return False
            return reply.strip().lower() in ("y", "yes", "好", "批准")
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
