"""QQ 渠道会话存储
==================

实现 QQSession 和 QQSessionStore，模式与 FeishuSessionStore 一致。
会话以 JSON 文件持久化到磁盘。

类说明：
    - QQSession: 单个会话的数据容器
    - QQSessionStore: 会话存储管理器
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from illusion.channels.base import InboundMessage

logger = logging.getLogger(__name__)


@dataclass
class QQSession:
    """QQ 渠道会话

    Attributes:
        key: 会话键（chat_id 或 chat_id_user_id）
        user_id: 用户标识
        chat_type: 会话类型（dm / group）
        messages: 对话历史
        session_id: agent 会话 ID（用于恢复）
        model: 当前使用的模型
    """

    key: str
    user_id: str
    chat_type: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    session_id: str = ""
    model: str = ""


class QQSessionStore:
    """QQ 渠道会话存储

    会话以 JSON 文件存储在 data_dir 下，key 作为文件名。

    Attributes:
        data_dir: 存储目录
        group_sessions_per_user: 群组会话是否按用户隔离
    """

    def __init__(self, data_dir: Path, group_sessions_per_user: bool = True) -> None:
        """初始化存储

        Args:
            data_dir: 会话文件存储目录
            group_sessions_per_user: 群组会话是否按用户隔离
        """
        self.data_dir = data_dir
        self.group_sessions_per_user = group_sessions_per_user
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def build_session_key(self, msg: InboundMessage) -> str:
        """构建会话键

        私聊：chat_id
        群聊（隔离）：chat_id_user_id
        群聊（不隔离）：chat_id

        Args:
            msg: 入站消息

        Returns:
            str: 会话键
        """
        if msg.chat_type == "group" and self.group_sessions_per_user:
            return f"{msg.chat_id}_{msg.user_id}"
        return msg.chat_id

    def get_or_create(self, key: str, user_id: str, chat_type: str) -> QQSession:
        """获取或创建会话

        Args:
            key: 会话键
            user_id: 用户 ID
            chat_type: 会话类型

        Returns:
            QQSession: 会话实例
        """
        path = self._session_path(key)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return QQSession(
                    key=key,
                    user_id=data.get("user_id", user_id),
                    chat_type=data.get("chat_type", chat_type),
                    messages=data.get("messages", []),
                    session_id=data.get("session_id", ""),
                    model=data.get("model", ""),
                )
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("QQ 会话文件损坏，重新创建: %s", exc)

        return QQSession(key=key, user_id=user_id, chat_type=chat_type)

    def save(self, session: QQSession, messages: list[dict[str, Any]]) -> None:
        """保存会话到磁盘

        Args:
            session: 会话实例
            messages: 要持久化的消息列表
        """
        session.messages = messages
        path = self._session_path(session.key)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "user_id": session.user_id,
            "chat_type": session.chat_type,
            "messages": session.messages,
            "session_id": session.session_id,
            "model": session.model,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def check_signal(self) -> bool:
        """检查是否有 /delete 信号"""
        signal_path = self.data_dir / ".signal"
        if signal_path.exists():
            signal_path.unlink()
            return True
        return False

    def clear_signal(self) -> None:
        """清除 /delete 信号"""
        signal_path = self.data_dir / ".signal"
        if signal_path.exists():
            signal_path.unlink()

    def _session_path(self, key: str) -> Path:
        """会话文件路径"""
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self.data_dir / f"{safe_key}.json"
