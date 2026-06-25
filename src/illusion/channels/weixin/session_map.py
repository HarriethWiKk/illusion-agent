"""微信会话存储
==============

管理 user_id → 微信独立会话的映射。
结构与 FeishuSessionStore 相同，独立目录存储。

类说明：
    - WeixinSession: 单个微信会话状态
    - WeixinSessionStore: 会话存储管理器
"""
from __future__ import annotations

from typing import Any
import json
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from illusion.channels.base import InboundMessage


@dataclass
class WeixinSession:
    """微信会话状态

    Attributes:
        session_id: 会话唯一标识
        key: 存储键
        messages: 对话历史（dict[str, Any] 列表）
        user_id: 关联用户
        chat_type: 会话类型
        model: 会话使用的模型
    """

    session_id: str
    key: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    user_id: str = ""
    chat_type: str = "dm"
    model: str = ""


class WeixinSessionStore:
    """微信会话存储管理器

    微信 bot 只能私聊，按 user_id 隔离会话。

    Attributes:
        data_dir: 会话数据目录
    """

    def __init__(self, data_dir: Path) -> None:
        """初始化

        Args:
            data_dir: 会话数据目录
        """
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def build_session_key(self, msg: InboundMessage) -> str:
        """构造会话隔离键（微信只私聊，按 user_id）

        Args:
            msg: 入站消息

        Returns:
            str: 会话隔离键
        """
        return f"u:{msg.user_id}"

    def _key_to_path(self, key: str) -> Path:
        """将存储键转为文件路径

        Args:
            key: 存储键

        Returns:
            Path: 对应的 JSON 文件路径
        """
        safe = key.replace(":", "_").replace("/", "_")
        return self.data_dir / f"{safe}.json"

    def get_or_create(self, key: str, user_id: str, chat_type: str) -> WeixinSession:
        """获取或创建会话

        Args:
            key: 存储键
            user_id: 用户 ID
            chat_type: 会话类型

        Returns:
            WeixinSession: 会话状态
        """
        path = self._key_to_path(key)
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                return WeixinSession(
                    session_id=raw.get("session_id", uuid4().hex[:12]),
                    key=key,
                    messages=raw.get("messages", []),
                    user_id=raw.get("user_id", user_id),
                    chat_type=raw.get("chat_type", chat_type),
                    model=raw.get("model", ""),
                )
            except (json.JSONDecodeError, ValueError):
                pass  # 损坏则重建
        return WeixinSession(
            session_id=uuid4().hex[:12],
            key=key, messages=[], user_id=user_id, chat_type=chat_type,
        )

    def save(self, session: WeixinSession, messages: list[dict[str, Any]]) -> None:
        """保存会话历史

        Args:
            session: 会话状态
            messages: 最新的对话历史
        """
        session.messages = messages
        path = self._key_to_path(session.key)
        data = {
            "session_id": session.session_id,
            "messages": messages,
            "user_id": session.user_id,
            "chat_type": session.chat_type,
            "model": session.model,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def clear(self, key: str) -> None:
        """清空会话（删除文件）

        Args:
            key: 存储键
        """
        path = self._key_to_path(key)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def inject(self, key: str, messages: list[dict[str, Any]]) -> None:
        """用外部消息替换会话历史（/resume 用）

        Args:
            key: 存储键
            messages: 注入的消息列表
        """
        existing = self.get_or_create(key, "", "dm")
        existing.messages = messages
        self.save(existing, messages)

    def set_model(self, key: str, model: str) -> None:
        """设置会话模型（/model set 用）

        Args:
            key: 存储键
            model: 模型名称
        """
        existing = self.get_or_create(key, "", "dm")
        existing.model = model
        self.save(existing, existing.messages)
