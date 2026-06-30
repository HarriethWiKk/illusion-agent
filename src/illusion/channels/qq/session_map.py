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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from illusion.channels.base import InboundMessage, SessionInfo
from illusion.utils.atomic_write import atomic_write_text

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
        atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))

    def clear(self, key: str) -> None:
        """清空指定键的会话（删除文件）

        Args:
            key: 存储键
        """
        path = self._session_path(key)
        try:
            path.unlink()
        except FileNotFoundError:
            pass  # 已删除

    def _session_path(self, key: str) -> Path:
        """会话文件路径"""
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self.data_dir / f"{safe_key}.json"

    def list_active(self, limit: int = 5) -> list["SessionInfo"]:
        """列出最近活跃的 QQ 会话（按文件 mtime 排序）

        QQ 会话文件名为 chat_id（openid）或 chat_id_user_id（群组隔离）。
        chat_id 即文件名主体。

        Args:
            limit: 最多返回多少条

        Returns:
            list[SessionInfo]: 最近活跃会话，最新在前
        """
        files = sorted(
            self.data_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]
        result: list[SessionInfo] = []
        for path in files:
            name = path.stem
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError, OSError):
                continue
            # QQ: 文件名可能是 chat_id 或 chat_id_user_id
            # chat_id 即文件名（QQ openid 可能含下划线，保守用整个 name）
            chat_id = name
            chat_type = raw.get("chat_type", "dm")
            mtime = path.stat().st_mtime
            last_active = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
            result.append(SessionInfo(
                chat_id=chat_id,
                user_name=raw.get("user_id", "") or "",
                chat_type=chat_type,
                last_active=last_active,
            ))
        return result
