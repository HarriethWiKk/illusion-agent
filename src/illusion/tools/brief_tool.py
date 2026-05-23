"""
用户消息工具
============

本模块提供向用户发送消息的功能，支持 Markdown 格式和文件附件。

主要组件：
    - BriefTool: 向用户发送消息的工具

使用示例：
    >>> from illusion.tools import BriefTool
    >>> tool = BriefTool()
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult

# 图片文件扩展名集合
_IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
})


def _get_media_type(path: Path) -> str:
    """获取文件的 MIME 类型。"""
    media_type, _ = mimetypes.guess_type(str(path))
    if media_type:
        return media_type
    fallback: dict[str, str] = {".svg": "image/svg+xml"}
    return fallback.get(path.suffix.lower(), "application/octet-stream")


def _resolve_path(base: Path, candidate: str) -> Path:
    """解析相对路径为绝对路径。"""
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


class BriefToolInput(BaseModel):
    """简短消息发送参数。

    属性：
        message: 要发送给用户的消息，支持 Markdown
        attachments: 可选的附件文件路径列表（图片、diff、日志等）
        status: 消息意图标签（normal/proactive）
    """

    message: str = Field(description="Message to send to the user (supports markdown)")
    attachments: list[str] | None = Field(
        default=None,
        description="Optional file paths for attachments (images, diffs, logs)",
    )
    status: Literal["normal", "proactive"] | None = Field(
        default="normal",
        description="Intent label: 'normal' for replies, 'proactive' for initiations",
    )


class BriefTool(BaseTool):
    """向用户发送消息。

    这是模型与用户之间的主要通信通道。模型应通过此工具发送
    所有面向用户的消息，而不是依赖外部文本输出。
    支持 Markdown 格式和文件附件（图片、diff、日志等）。
    """

    name = "brief"
    description = """Send a message the user will read. Text outside this tool is visible in the detail view, but most won't open it — the answer lives here.

`message` supports markdown. `attachments` takes file paths (absolute or cwd-relative) for images, diffs, logs.

`status` labels intent: 'normal' when replying to what they just asked; 'proactive' when you're initiating — a scheduled task finished, a blocker surfaced during background work, you need input on something they haven't asked about. Set it honestly; downstream routing uses it.

## Talking to the user

SendUserMessage is where your replies go. Text outside it is visible if the user expands the detail view, but most won't — assume unread. Anything you want them to actually see goes through SendUserMessage. The failure mode: the real answer lives in plain text while SendUserMessage just says "done!" — they see "done!" and miss everything.

So: every time the user says something, the reply they actually read comes through SendUserMessage. Even for "hi". Even for "thanks".

If you can answer right away, send the answer. If you need to go look — run a command, read files, check something — ack first in one line ("On it — checking the test output"), then work, then send the result. Without the ack they're staring at a spinner.

For longer work: ack → work → result. Between those, send a checkpoint when something useful happened — a decision you made, a surprise you hit, a phase boundary. Skip the filler ("running tests...") — a checkpoint earns its place by carrying information.

Keep messages tight — the decision, the file:line, the PR number. Second person always ("your config"), never third."""
    input_model = BriefToolInput

    async def execute(self, arguments: BriefToolInput, context: ToolExecutionContext) -> ToolResult:
        message = arguments.message.strip()
        status = arguments.status or "normal"
        attachments = arguments.attachments or []

        metadata: dict[str, str] = {"status": status}

        output_parts = [message]

        if attachments:
            # 仅处理第一个附件（含媒体的 ToolResultBlock content 为列表时取第一个）
            # 后续附件以文本引用形式呈现
            primary_path = _resolve_path(context.cwd, attachments[0])
            if primary_path.exists() and primary_path.is_file():
                if primary_path.suffix.lower() in _IMAGE_EXTENSIONS:
                    raw = primary_path.read_bytes()
                    media_type = _get_media_type(primary_path)
                    encoded = base64.b64encode(raw).decode("ascii")
                    metadata.update({
                        "media_category": "image",
                        "media_type": media_type,
                        "media_data": encoded,
                        "media_path": str(primary_path),
                        "media_size": str(len(raw)),
                    })

            # 所有附件以文本形式列出
            attachment_lines = []
            for file_path in attachments:
                resolved = _resolve_path(context.cwd, file_path)
                if resolved.exists() and resolved.is_file():
                    size = resolved.stat().st_size
                    kb = f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} B"
                    attachment_lines.append(f"- `{resolved}` ({kb})")
                else:
                    attachment_lines.append(f"- `{resolved}` (not found)")
            output_parts.append("\nAttachments:\n" + "\n".join(attachment_lines))

        full_output = "\n".join(output_parts)
        return ToolResult(output=full_output, metadata=metadata)
