"""飞书云盘工具
==============

提供 agent 可调用的飞书云盘文件操作工具。

工具说明：
    - FeishuDriveListTool: 列出云盘文件夹下的文件
    - FeishuDriveUploadTool: 上传本地文件到云盘
    - FeishuDriveDownloadTool: 下载云盘文件到本地
"""
from __future__ import annotations

from pathlib import Path  # 路径
from typing import TYPE_CHECKING  # 类型

from pydantic import BaseModel, Field  # 数据模型

from illusion.channels.feishu.messaging import build_lark_client  # 客户端构造
from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult  # 工具基类

if TYPE_CHECKING:
    from illusion.channels.config import FeishuChannelConfig  # 配置


class FeishuDriveListInput(BaseModel):
    """飞书云盘列表工具输入

    Attributes:
        folder_token: 文件夹 token（默认根目录）
        page_size: 每页数量（默认 50）
    """

    folder_token: str = Field("", description="Folder token (empty for root)")
    page_size: int = Field(50, description="Page size (max 200)")


class FeishuDriveListTool(BaseTool):
    """列出飞书云盘文件夹下的文件"""

    name = "feishu_drive_list"
    description = "List files in a Feishu/Lark Drive folder."
    input_model = FeishuDriveListInput

    def __init__(self, channel_config: "FeishuChannelConfig") -> None:
        """初始化

        Args:
            channel_config: 飞书渠道配置
        """
        self._cfg = channel_config

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        """执行云盘列表

        Args:
            arguments: 输入参数（FeishuDriveListInput）
            context: 执行上下文

        Returns:
            ToolResult: 文件列表或错误
        """
        assert isinstance(arguments, FeishuDriveListInput)
        client = build_lark_client(self._cfg)
        try:
            from lark_oapi.api.drive.v1 import (  # type: ignore[import-not-found]
                ListFileRequest,
            )
        except ImportError:
            return ToolResult(output="lark_oapi drive API not available", is_error=True)

        # lark-oapi 使用 builder 模式构造请求
        req = (
            ListFileRequest.builder()
            .page_size(arguments.page_size)
            .folder_token(arguments.folder_token)
            .build()
        )
        resp = client.drive.v1.file.list(req)
        if not resp.success():
            return ToolResult(
                output=f"Failed to list files: code={resp.code} msg={resp.msg}",
                is_error=True,
            )
        files = getattr(getattr(resp, "data", None), "files", []) or []
        lines = []
        for f in files:
            name = getattr(f, "name", "?")
            token = getattr(f, "file_token", "?")
            ftype = getattr(f, "type", "?")
            lines.append(f"- {name} [{ftype}] token={token}")
        return ToolResult(output="\n".join(lines) if lines else "(empty folder)")


class FeishuDriveUploadInput(BaseModel):
    """飞书云盘上传工具输入

    Attributes:
        file_path: 本地文件路径
        folder_token: 目标文件夹 token（可选）
        name: 云盘文件名（可选，默认用本地文件名）
    """

    file_path: str = Field(..., description="Local file path to upload")
    folder_token: str = Field("", description="Target folder token (optional)")
    name: str = Field("", description="Cloud file name (defaults to local name)")


class FeishuDriveUploadTool(BaseTool):
    """上传本地文件到飞书云盘"""

    name = "feishu_drive_upload"
    description = "Upload a local file to Feishu/Lark Drive."
    input_model = FeishuDriveUploadInput

    def __init__(self, channel_config: "FeishuChannelConfig") -> None:
        """初始化

        Args:
            channel_config: 飞书渠道配置
        """
        self._cfg = channel_config

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        """执行文件上传

        Args:
            arguments: 输入参数（FeishuDriveUploadInput）
            context: 执行上下文

        Returns:
            ToolResult: 上传结果（含 file_token）或错误
        """
        assert isinstance(arguments, FeishuDriveUploadInput)
        path = Path(arguments.file_path)
        if not path.exists():
            return ToolResult(output=f"File not found: {arguments.file_path}", is_error=True)
        client = build_lark_client(self._cfg)
        try:
            from lark_oapi.api.drive.v1 import (  # type: ignore[import-not-found]
                UploadAllFileRequest,
            )
        except ImportError:
            return ToolResult(output="lark_oapi drive API not available", is_error=True)

        name = arguments.name or path.name
        # lark-oapi 用 builder + dict 构造请求（RequestBody 类不接受关键字参数）
        body = {
            "folder_token": arguments.folder_token,
            "file_name": name,
            "file": path.read_bytes(),
        }
        req = UploadAllFileRequest.builder().request_body(body).build()
        resp = client.drive.v1.file.upload_all(req)
        if not resp.success():
            return ToolResult(
                output=f"Upload failed: code={resp.code} msg={resp.msg}",
                is_error=True,
            )
        data = getattr(resp, "data", None)
        token = getattr(data, "file_token", "?") if data else "?"
        return ToolResult(output=f"Uploaded: {name} token={token}")


class FeishuDriveDownloadInput(BaseModel):
    """飞书云盘下载工具输入

    Attributes:
        file_token: 云盘文件 token
        file_type: 文件类型（docx/sheet/file 等）
        save_path: 本地保存路径
    """

    file_token: str = Field(..., description="Cloud file token")
    file_type: str = Field("file", description="File type (docx/sheet/file)")
    save_path: str = Field(..., description="Local save path")


class FeishuDriveDownloadTool(BaseTool):
    """下载飞书云盘文件到本地"""

    name = "feishu_drive_download"
    description = "Download a Feishu/Lark Drive file to local path."
    input_model = FeishuDriveDownloadInput

    def __init__(self, channel_config: "FeishuChannelConfig") -> None:
        """初始化

        Args:
            channel_config: 飞书渠道配置
        """
        self._cfg = channel_config

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        """执行文件下载

        Args:
            arguments: 输入参数（FeishuDriveDownloadInput）
            context: 执行上下文

        Returns:
            ToolResult: 下载结果或错误
        """
        assert isinstance(arguments, FeishuDriveDownloadInput)
        client = build_lark_client(self._cfg)
        try:
            from lark_oapi.api.drive.v1 import (  # type: ignore[import-not-found]
                DownloadFileRequest,
            )
        except ImportError:
            return ToolResult(output="lark_oapi drive API not available", is_error=True)

        req = DownloadFileRequest.builder().file_token(arguments.file_token).file_type(arguments.file_type).build()
        resp = client.drive.v1.file.download(req)
        if not resp.success():
            return ToolResult(
                output=f"Download failed: code={resp.code} msg={resp.msg}",
                is_error=True,
            )
        # resp 里有文件流，写入本地
        raw = getattr(resp, "file", None)
        if raw is None:
            return ToolResult(output="No file data returned", is_error=True)
        save_path = Path(arguments.save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(raw.read() if hasattr(raw, "read") else bytes(raw))
        return ToolResult(output=f"Downloaded to: {save_path}")
