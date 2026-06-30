"""飞书会话存储
==============

管理 chat_id → 飞书独立会话的映射，支持拉取/保存本地 session。

会话历史独立存于 ~/.illusion/channels/feishu/sessions/<key>.json，
与本地终端 session 隔离，但可通过 /resume /detach 互通。

类说明：
    - FeishuSession: 单个飞书会话状态
    - FeishuSessionStore: 会话存储管理器
"""
from __future__ import annotations

from typing import Any
import json  # JSON 读写
import time  # 时间处理（list_active 用）
from dataclasses import dataclass, field  # 数据类
from pathlib import Path  # 路径处理
from uuid import uuid4  # 会话 ID 生成

from illusion.channels.base import InboundMessage, SessionInfo  # 入站消息类型 / 会话摘要
from illusion.utils.atomic_write import atomic_write_text  # 原子写入工具


@dataclass
class FeishuSession:
    """飞书会话状态

    Attributes:
        session_id: 会话唯一标识
        key: 存储键（build_session_key 生成）
        messages: 对话历史（dict[str, Any] 列表，与 session_storage 格式一致）
        user_id: 关联用户
        chat_type: 会话类型
        model: 会话使用的模型（可被 /model 覆盖）
    """

    session_id: str  # 会话 ID
    key: str  # 存储键
    messages: list[dict[str, Any]] = field(default_factory=list)  # 对话历史
    user_id: str = ""  # 用户 ID
    chat_type: str = "dm"  # 会话类型
    model: str = ""  # 会话模型


class FeishuSessionStore:
    """飞书会话存储管理器

    按 session key（DM 用 user_id，群组用 chat_id+user_id）隔离会话。

    Attributes:
        data_dir: 会话数据目录
        group_sessions_per_user: 群组会话是否按用户隔离
    """

    def __init__(self, data_dir: Path, group_sessions_per_user: bool = True) -> None:
        """初始化

        Args:
            data_dir: 会话数据目录
            group_sessions_per_user: 群组会话是否按用户隔离
        """
        self.data_dir = data_dir  # 数据目录
        self.group_sessions_per_user = group_sessions_per_user  # 群组隔离开关
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def build_session_key(self, msg: InboundMessage) -> str:
        """根据入站消息构造会话隔离键

        移植自 hermes 的 build_session_key 逻辑：
        - 私聊：每用户独立
        - 群组：默认每用户每群独立，可配置为群共享

        Args:
            msg: 入站消息

        Returns:
            str: 会话隔离键
        """
        if msg.chat_type == "group":
            if self.group_sessions_per_user:
                return f"g:{msg.chat_id}:{msg.user_id}"  # 群内每用户独立
            return f"g:{msg.chat_id}"  # 群共享
        return f"u:{msg.user_id}"  # 私聊每用户独立

    def _key_to_path(self, key: str) -> Path:
        """将存储键转为文件路径

        键中的冒号替换为下划线作为安全文件名。

        Args:
            key: 存储键

        Returns:
            Path: 对应的 JSON 文件路径
        """
        safe = key.replace(":", "_").replace("/", "_")  # 安全文件名
        return self.data_dir / f"{safe}.json"

    def get_or_create(self, key: str, user_id: str, chat_type: str) -> FeishuSession:
        """获取或创建会话

        文件存在则读回，不存在则新建空会话。

        Args:
            key: 存储键
            user_id: 用户 ID
            chat_type: 会话类型

        Returns:
            FeishuSession: 会话状态
        """
        path = self._key_to_path(key)
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                return FeishuSession(
                    session_id=raw.get("session_id", uuid4().hex[:12]),
                    key=key,
                    messages=raw.get("messages", []),
                    user_id=raw.get("user_id", user_id),
                    chat_type=raw.get("chat_type", chat_type),
                    model=raw.get("model", ""),
                )
            except (json.JSONDecodeError, ValueError):
                pass  # 损坏则重建
        return FeishuSession(
            session_id=uuid4().hex[:12],  # 新 ID
            key=key,
            messages=[],
            user_id=user_id,
            chat_type=chat_type,
        )

    def save(self, session: FeishuSession, messages: list[dict[str, Any]]) -> None:
        """保存会话历史

        Args:
            session: 会话状态
            messages: 最新的对话历史
        """
        session.messages = messages  # 更新内存
        path = self._key_to_path(session.key)
        data = {
            "session_id": session.session_id,
            "messages": messages,
            "user_id": session.user_id,
            "chat_type": session.chat_type,
            "model": session.model,
        }
        atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))

    def clear(self, key: str) -> None:
        """清空指定键的会话（删除文件）

        Args:
            key: 存储键
        """
        path = self._key_to_path(key)
        try:
            path.unlink()
        except FileNotFoundError:
            pass  # 已删除

    def clear_by_session_id(self, session_id: str) -> bool:
        """按 session_id 删除会话文件（用于 /delete 命令跨渠道清理）

        遍历所有 JSON 文件，找到匹配的 session_id 并删除。

        Args:
            session_id: 要删除的会话 ID

        Returns:
            bool: 找到并删除返回 True
        """
        for path in self.data_dir.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if raw.get("session_id") == session_id:
                    path.unlink()
                    return True
            except (json.JSONDecodeError, ValueError, OSError):
                continue
        return False

    def inject(self, key: str, messages: list[dict[str, Any]]) -> None:
        """用外部消息替换指定键的会话历史（用于 /resume）

        Args:
            key: 存储键
            messages: 注入的消息列表
        """
        existing = self.get_or_create(key, "", "dm")
        existing.messages = messages
        self.save(existing, messages)

    def set_model(self, key: str, model: str) -> None:
        """设置指定键会话使用的模型（用于 /model set）

        Args:
            key: 存储键
            model: 模型名称
        """
        existing = self.get_or_create(key, "", "dm")
        existing.model = model
        self.save(existing, existing.messages)

    def list_active(self, limit: int = 5) -> list["SessionInfo"]:
        """列出最近活跃的会话（按文件 mtime 排序）

        扫描 data_dir/*.json，反推 chat_id 和 user_id。
        文件名格式：u_<user_id>.json（私聊）或 g_<chat_id>_<user_id>.json（群聊）。

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
            name = path.stem  # 去 .json
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError, OSError):
                continue
            # 反推 chat_id 和 chat_type
            if name.startswith("u_"):
                # 私聊：u_<user_id>，chat_id 即 user_id
                chat_id = name[2:]
                chat_type = "dm"
            elif name.startswith("g_"):
                # 群聊：g_<chat_id>_<user_id>，飞书 chat_id 以 oc_ 开头，user_id 以 ou_ 开头
                remainder = name[2:]
                # 找到 oc_ 开头的部分作为 chat_id，再用 _ou_ 截断去掉 user_id
                if "oc_" in remainder:
                    idx = remainder.index("oc_")
                    chat_id = remainder[idx:]
                    if "_ou_" in chat_id:
                        chat_id = chat_id[:chat_id.index("_ou_")]
                else:
                    chat_id = remainder
                chat_type = "group"
            else:
                chat_id = name
                chat_type = "dm"
            mtime = path.stat().st_mtime
            last_active = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
            result.append(SessionInfo(
                chat_id=chat_id,
                user_name=raw.get("user_id", "") or "",
                chat_type=chat_type,
                last_active=last_active,
            ))
        return result
