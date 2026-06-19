"""通用斜杠命令处理器基类
================================

从 FeishuCommandHandler 提取的通用逻辑，飞书/微信等渠道共用。
支持命令：/help /clear /new /sessions /resume /detach /model

类说明：
    - BaseCommandHandler: 通用命令处理器基类
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from illusion.channels.base import InboundMessage
from illusion.config.i18n import t

if TYPE_CHECKING:
    from illusion.channels.base import Channel


class BaseCommandHandler:
    """通用斜杠命令处理器

    在 agent 处理前拦截 / 命令，处理会话管理操作。
    子类只需提供 channel 和 session_store。

    Attributes:
        channel: 渠道实例（用于发消息）
        session_store: 会话存储
    """

    def __init__(self, channel: "Channel", session_store) -> None:
        """初始化

        Args:
            channel: 渠道实例
            session_store: 会话存储
        """
        self.channel = channel
        self.session_store = session_store

    async def try_handle(self, msg: InboundMessage) -> bool:
        """尝试处理斜杠命令

        Args:
            msg: 入站消息

        Returns:
            bool: 是斜杠命令并已处理返回 True，否则 False（交由 agent）
        """
        text = msg.text.strip()
        if not text.startswith("/"):
            return False

        key = self.session_store.build_session_key(msg)
        parts = text[1:].split(None, 1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "help":
            await self.channel.send_text(msg.chat_id, t("feishu_cmd_help"))
        elif cmd == "clear":
            self.session_store.clear(key)
            await self.channel.send_text(msg.chat_id, t("feishu_cmd_cleared"))
        elif cmd == "new":
            self.session_store.clear(key)
            await self.channel.send_text(msg.chat_id, t("feishu_cmd_new"))
        elif cmd == "model":
            await self._cmd_model(msg, key, args)
        elif cmd == "sessions":
            await self._cmd_sessions(msg)
        elif cmd == "resume":
            await self._cmd_resume(msg, key, args)
        elif cmd == "detach":
            await self._cmd_detach(msg, key)
        else:
            await self.channel.send_text(msg.chat_id, t("feishu_cmd_unknown", cmd=f"/{cmd}"))
        return True

    async def _cmd_model(self, msg, key, args):
        """处理 /model 命令

        Args:
            msg: 入站消息
            key: 会话键
            args: 命令参数
        """
        if not args or args.lower() == "show":
            session = self.session_store.get_or_create(key, msg.user_id, msg.chat_type)
            model = session.model or "（默认）"
            await self.channel.send_text(msg.chat_id, t("feishu_cmd_model_show", model=model))
            return
        parts = args.split(None, 1)
        if parts[0].lower() == "set" and len(parts) > 1:
            model_name = parts[1].strip()
            self.session_store.set_model(key, model_name)
            await self.channel.send_text(msg.chat_id, t("feishu_cmd_model_set", model=model_name))
        else:
            await self.channel.send_text(msg.chat_id, t("feishu_cmd_model_usage"))

    async def _cmd_sessions(self, msg):
        """处理 /sessions 命令：列出本地终端会话

        Args:
            msg: 入站消息
        """
        from illusion.services.session_storage import list_session_snapshots

        cwd = str(Path.cwd())
        snapshots = list_session_snapshots(cwd)
        if not snapshots:
            await self.channel.send_text(msg.chat_id, t("feishu_cmd_no_sessions"))
            return
        lines = [t("feishu_cmd_sessions_title")]
        for i, s in enumerate(snapshots, 1):
            sid = s.get("session_id", "?")
            summary = s.get("summary", "?")[:50]
            count = s.get("message_count", 0)
            lines.append(f"  {i}. [{sid}] {summary} ({count} msgs)")
        await self.channel.send_text(msg.chat_id, "\n".join(lines))

    async def _cmd_resume(self, msg, key, args):
        """处理 /resume 命令：恢复本地会话

        Args:
            msg: 入站消息
            key: 会话键
            args: 命令参数（序号或 session_id）
        """
        from illusion.services.session_storage import list_session_snapshots, load_session_by_id

        cwd = str(Path.cwd())
        snapshots = list_session_snapshots(cwd)
        if not snapshots:
            await self.channel.send_text(msg.chat_id, t("feishu_cmd_no_sessions"))
            return
        chosen = None
        if args:
            try:
                idx = int(args) - 1
                if 0 <= idx < len(snapshots):
                    chosen = snapshots[idx]
            except ValueError:
                pass
            if chosen is None:
                chosen = next((s for s in snapshots if s.get("session_id") == args), None)
        if chosen is None:
            lines = [t("feishu_cmd_sessions_title")]
            for i, s in enumerate(snapshots, 1):
                sid = s.get("session_id", "?")
                summary = s.get("summary", "?")[:50]
                lines.append(f"  {i}. [{sid}] {summary}")
            await self.channel.send_text(msg.chat_id, "\n".join(lines))
            return
        data = load_session_by_id(cwd, chosen.get("session_id", ""))
        if data is None:
            await self.channel.send_text(msg.chat_id, t("feishu_cmd_no_sessions"))
            return
        messages = data.get("messages", [])
        self.session_store.inject(key, messages)
        await self.channel.send_text(msg.chat_id, t("feishu_cmd_resumed", n=len(messages)))

    async def _cmd_detach(self, msg, key):
        """处理 /detach 命令：保存为本地 session

        Args:
            msg: 入站消息
            key: 会话键
        """
        from illusion.engine.messages import ConversationMessage
        from illusion.services.session_storage import save_session_snapshot

        session = self.session_store.get_or_create(key, msg.user_id, msg.chat_type)
        cwd = str(Path.cwd())
        conv_messages = []
        for m in session.messages:
            try:
                conv_messages.append(ConversationMessage.model_validate(m))
            except (ValueError, TypeError):
                continue
        from illusion.config import load_settings
        from illusion.api.usage import UsageSnapshot
        settings = load_settings()
        save_session_snapshot(
            cwd=cwd, model=session.model or settings.active_model_name,
            system_prompt="", messages=conv_messages,
            usage=UsageSnapshot(), session_id=session.session_id,
        )
        await self.channel.send_text(msg.chat_id, t("feishu_cmd_detached", id=session.session_id))
