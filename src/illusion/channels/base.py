"""渠道抽象基类
================

定义所有消息渠道（飞书、未来的 telegram 等）的统一接口。

类说明：
    - InboundMessage: 标准化的入站消息
    - Channel: 渠道抽象基类

设计原则：精简接口，只保留飞书渠道当前需要的能力。
未来新增渠道若有额外需求，再扩展基类。
"""
from __future__ import annotations

from abc import ABC, abstractmethod  # 抽象基类支持
from dataclasses import dataclass  # 数据类
from typing import TYPE_CHECKING, Any, AsyncIterator  # 类型注解

if TYPE_CHECKING:
    from illusion.config.settings import Settings  # 仅类型检查时导入，避免循环


@dataclass(frozen=True)
class InboundMessage:
    """标准化入站消息

    所有渠道的原始事件归一化为此结构后，再交给 ChannelRunner 处理。

    Attributes:
        text: 消息文本内容
        chat_id: 会话标识（飞书 DM 用 open_id，群组用 chat_id）
        chat_type: 会话类型，dm（私聊）或 group（群聊）
        user_id: 发送者标识（飞书 open_id）
        user_name: 发送者显示名
        message_id: 入站消息 ID，用于回复定位
        is_bot: 发送者是否为机器人
        thread_id: 话题/线程 ID（可选）
    """

    text: str  # 消息文本
    chat_id: str  # 会话标识
    chat_type: str  # "dm" | "group"
    user_id: str  # 发送者 ID
    user_name: str  # 发送者名
    message_id: str  # 消息 ID
    is_bot: bool = False  # 是否机器人
    thread_id: str = ""  # 线程 ID


class Channel(ABC):
    """消息渠道抽象基类

    子类需实现连接、监听、收发、关闭等核心方法。

    Attributes:
        name: 渠道名称（如 "feishu"）
    """

    name: str  # 子类设置

    def __init__(self, config: Any, settings: "Settings") -> None:
        """初始化渠道

        Args:
            config: 渠道特定配置（如 FeishuChannelConfig）
            settings: illusion 主设置（用于获取模型、API key 等）
        """
        self.config = config  # 渠道配置
        self.settings = settings  # 主设置

    @abstractmethod
    async def connect(self) -> None:
        """建立渠道连接（如 WS 长连接）"""
        ...

    @abstractmethod
    def listen(self) -> AsyncIterator[InboundMessage]:
        """返回入站消息的异步迭代器

        实现应为 async generator，不断 yield InboundMessage。
        """
        ...

    @abstractmethod
    async def send_text(self, chat_id: str, text: str, *, reply_to: str = "") -> str:
        """发送文本消息，返回新消息 ID

        Args:
            chat_id: 目标会话
            text: 文本内容（纯文本或 markdown）
            reply_to: 要回复的消息 ID（可选）

        Returns:
            str: 新发送的消息 ID
        """
        ...

    @abstractmethod
    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        """编辑已发送消息的文本（用于流式编辑）

        Args:
            chat_id: 会话标识
            message_id: 要编辑的消息 ID
            text: 新文本内容
        """
        ...

    @abstractmethod
    async def send_file(self, chat_id: str, file_path: str) -> None:
        """发送文件

        Args:
            chat_id: 目标会话
            file_path: 本地文件路径
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭渠道连接，释放资源"""
        ...
