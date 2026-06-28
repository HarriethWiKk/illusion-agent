"""跨渠道文件传输工具

提供 LLM 可调用的跨渠道文件投递工具。当用户要求把文件发送到
另一个渠道（如 QQ → 微信，或 PC 终端 → 飞书）时使用。

工具说明：
    - ListChannelSessionsTool: 列出指定渠道的活跃会话（查找 chat_id）
    - SendToChannelTool: 发送本地文件到指定渠道会话

工作流：
    1. 用户要求跨渠道发文件（如"把这个文件发到微信"）
    2. LLM 先调 list_channel_sessions 查找目标渠道的活跃会话
    3. LLM 拿到会话列表后，用 ask_user_question 询问用户确认目标 chat_id
    4. 用户确认后，LLM 调 send_to_channel 发送文件

设计原则：与 SendMediaTool 互补——SendMediaTool 用于当前渠道内发文件，
SendToChannelTool 用于跨渠道发文件。LLM 根据用户意图选择。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from illusion.channels.delivery import deliver_file_to_channel
from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult

if TYPE_CHECKING:
    from illusion.channels.config import ChannelsConfig


class ListChannelSessionsInput(BaseModel):
    """查找渠道活跃会话工具输入

    Attributes:
        channel_name: 目标渠道名 "feishu"/"qq"/"weixin"
        limit: 最多返回多少条会话（默认 10）
    """

    channel_name: str = Field(..., description="Target channel: feishu/qq/weixin")
    limit: int = Field(default=10, description="Max sessions to return (default 10)")


class ListChannelSessionsTool(BaseTool[ListChannelSessionsInput]):
    """列出指定渠道的活跃会话

    当用户要求跨渠道发文件但未指定具体 chat_id 时，先调用此工具
    查找目标渠道的活跃会话列表，然后询问用户确认要发送到哪个会话。

    返回的会话列表包含 chat_id、user_name（如有）、chat_type、last_active。
    LLM 应将这些信息呈现给用户，让用户选择目标会话。
    """

    name = "list_channel_sessions"
    description = (
        "List active sessions in a messaging channel to find a target chat_id. "
        "Use this FIRST when the user asks to send a file to another channel "
        "but hasn't specified a chat_id. After getting the session list, "
        "present the options to the user and ask which one to send to. "
        "Do NOT ask the user for a chat_id directly — most users don't know it."
    )
    input_model = ListChannelSessionsInput

    def __init__(self, config: "ChannelsConfig") -> None:
        """初始化

        Args:
            config: 全部渠道配置（用于校验目标渠道是否 enabled）
        """
        self._config = config

    async def execute(
        self, arguments: BaseModel, context: ToolExecutionContext
    ) -> ToolResult:
        """执行会话查找"""
        assert isinstance(arguments, ListChannelSessionsInput)

        # 校验目标渠道是否启用
        target_cfg = getattr(self._config, arguments.channel_name, None)
        if target_cfg is None or not getattr(target_cfg, "enabled", False):
            return ToolResult(
                output=f"Channel '{arguments.channel_name}' is not enabled",
                is_error=True,
            )

        try:
            from illusion.prompts.channel_hints import list_active_sessions

            sessions = list_active_sessions(
                arguments.channel_name, self._config, limit=arguments.limit,
            )
            if not sessions:
                return ToolResult(
                    output=(
                        f"No active sessions found in '{arguments.channel_name}'. "
                        "The user may need to interact with the bot in that channel first."
                    )
                )

            # 格式化会话列表
            lines = [f"Active sessions in '{arguments.channel_name}' (most recent first):"]
            for i, s in enumerate(sessions, 1):
                parts = [f"{i}. chat_id={s.chat_id}"]
                if s.user_name and s.user_name != s.chat_id:
                    parts.append(f"user={s.user_name}")
                if s.chat_type:
                    parts.append(f"[{s.chat_type}]")
                if s.last_active:
                    parts.append(f"last_active={s.last_active}")
                lines.append(" | ".join(parts))
            lines.append("")
            lines.append(
                "Present these options to the user and ask which one to send the file to. "
                "Do NOT proceed to send without user confirmation."
            )
            return ToolResult(output="\n".join(lines))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                output=f"Failed to list sessions: {exc}", is_error=True
            )


class SendToChannelInput(BaseModel):
    """跨渠道文件投递工具输入

    Attributes:
        channel_name: 目标渠道名 "feishu"/"qq"/"weixin"
        chat_id: 目标渠道中的会话 ID（通过 list_channel_sessions 查找）
        file_path: 本地文件路径
        caption: 可选附注文字
    """

    channel_name: str = Field(..., description="Target channel: feishu/qq/weixin")
    chat_id: str = Field(
        ...,
        description=(
            "Target chat ID in that channel. "
            "Find it via this order: (1) call list_channel_sessions first; "
            "(2) if unavailable, manually check "
            "~/.illusion/channels/<channel>/sessions/ and strip the prefix; "
            "(3) only if both fail, ask the user."
        ),
    )
    file_path: str = Field(..., description="Local file path to send")
    caption: str = Field(default="", description="Optional caption text")


class SendToChannelTool(BaseTool[SendToChannelInput]):
    """发送本地文件到另一个渠道的会话

    当用户要求跨渠道传输文件时使用（如"把这个文件发到微信"）。
    对于当前渠道内发文件，应使用 send_media 工具。

    工作流：
        1. 用户要求跨渠道发文件
        2. 先调 list_channel_sessions 查找目标渠道的活跃会话
        3. 用 ask_user_question 询问用户确认目标 chat_id
        4. 用户确认后，调 send_to_channel 发送文件

    工具内部调用 deliver_file_to_channel 构造临时 API 客户端发送，
    不依赖当前渠道实例。
    """

    name = "send_to_channel"
    description = (
        "Send a local file to a user/group in ANOTHER messaging channel. "
        "Use this when the user asks to send a file to a different channel "
        "(e.g., from QQ to WeChat, or from PC terminal to Feishu). "
        "For sending within the current channel, use send_media instead. "
        "To find the target chat_id, follow this order: "
        "(1) PREFER calling list_channel_sessions first to show active "
        "sessions, then ask the user to confirm which one to send to; "
        "(2) if the tool is unavailable or returns nothing, manually check "
        "~/.illusion/channels/<channel>/sessions/ and strip the filename "
        "prefix (feishu 'u_ou_xxx.json' -> 'ou_xxx', 'g_oc_xxx_ou_xxx.json' "
        "-> 'oc_xxx'; weixin 'u_<wxid>.json' -> '<wxid>'; qq filename is the ID); "
        "(3) only if BOTH fail, ask the user for the chat_id directly. "
        "Do NOT ask the user for a chat_id without first trying (1) and (2) — "
        "most users don't know it."
    )
    input_model = SendToChannelInput

    def __init__(self, config: "ChannelsConfig") -> None:
        """初始化

        Args:
            config: 全部渠道配置（用于校验目标渠道是否 enabled）
        """
        self._config = config

    async def execute(
        self, arguments: BaseModel, context: ToolExecutionContext
    ) -> ToolResult:
        """执行跨渠道文件投递"""
        assert isinstance(arguments, SendToChannelInput)

        # 校验目标渠道是否启用
        target_cfg = getattr(self._config, arguments.channel_name, None)
        if target_cfg is None or not getattr(target_cfg, "enabled", False):
            return ToolResult(
                output=f"Channel '{arguments.channel_name}' is not enabled",
                is_error=True,
            )

        path = Path(arguments.file_path)
        if not path.exists():
            return ToolResult(
                output=f"File not found: {arguments.file_path}", is_error=True
            )

        try:
            success = await deliver_file_to_channel(
                arguments.channel_name,
                arguments.chat_id,
                arguments.file_path,
                config=self._config,
                caption=arguments.caption,
            )
            if success:
                return ToolResult(
                    output=f"Sent {path.name} to {arguments.channel_name}:{arguments.chat_id}"
                )
            return ToolResult(
                output=f"Failed to send to {arguments.channel_name}:{arguments.chat_id}",
                is_error=True,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                output=f"Failed to send to channel: {exc}", is_error=True
            )
