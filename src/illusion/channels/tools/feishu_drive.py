"""飞书云盘工具
==============

提供 agent 可调用的飞书云盘文件操作工具。

工具说明：
    - FeishuDriveListTool: 列出云盘文件夹下的文件
    - FeishuDriveUploadTool: 上传本地文件到云盘（>20MB 自动分片）
    - FeishuDriveDownloadTool: 下载云盘文件到本地
    - FeishuDriveMkdirTool: 创建文件夹
    - FeishuDriveDeleteTool: 删除文件（移至回收站）
"""
from __future__ import annotations

from pathlib import Path  # 路径
from typing import TYPE_CHECKING, Any  # 类型

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


class FeishuDriveListTool(BaseTool[FeishuDriveListInput]):
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
            from lark_oapi.api.drive.v1 import (  # type: ignore[import-untyped]
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
            url = getattr(f, "url", "")
            lines.append(f"- {name} [{ftype}] token={token} url={url}")
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


class FeishuDriveUploadTool(BaseTool[FeishuDriveUploadInput]):
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
        """执行文件上传（小文件用 upload_all，大文件用分片）

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

        file_size = path.stat().st_size
        client = build_lark_client(self._cfg)
        name = arguments.name or path.name

        if file_size > 20 * 1024 * 1024:  # > 20MB，分片上传
            return await self._upload_chunked(client, path, name, arguments.folder_token)
        return await self._upload_all(client, path, name, arguments.folder_token)

    async def _upload_all(self, client: Any, path: Path, name: str, folder_token: str) -> ToolResult:
        """小文件整文件上传"""
        try:
            from lark_oapi.api.drive.v1 import (
                UploadAllFileRequest,
            )
        except ImportError:
            return ToolResult(output="lark_oapi drive API not available", is_error=True)

        # lark-oapi 用 builder + dict[str, Any] 构造请求（RequestBody 类不接受关键字参数）
        body = {
            "folder_token": folder_token,
            "file_name": name,
            "file": path.read_bytes(),
        }
        req = UploadAllFileRequest.builder().request_body(body).build()  # pyright: ignore[reportArgumentType]
        resp = client.drive.v1.file.upload_all(req)
        if not resp.success():
            return ToolResult(
                output=f"Upload failed: code={resp.code} msg={resp.msg}",
                is_error=True,
            )
        data = getattr(resp, "data", None)
        token = getattr(data, "file_token", "?") if data else "?"
        return ToolResult(output=f"Uploaded: {name} token={token}")

    async def _upload_chunked(self, client: Any, path: Path, name: str, folder_token: str) -> ToolResult:
        """大文件分片上传"""
        try:
            from lark_oapi.api.drive.v1 import (
                UploadPrepareFileRequest,
                UploadPartFileRequest,
                UploadFinishFileRequest,
            )
        except ImportError:
            return ToolResult(output="lark_oapi drive API not available (chunked)", is_error=True)

        file_size = path.stat().st_size
        block_size = 4 * 1024 * 1024  # 4MB per part

        # 1. prepare
        prepare_body = {
            "file_name": name,
            "parent_type": "explorer",
            "parent_node": folder_token,
            "size": file_size,
        }
        req = UploadPrepareFileRequest.builder().request_body(prepare_body).build()  # pyright: ignore[reportArgumentType]
        resp = client.drive.v1.file.upload_prepare(req)
        if not resp.success():
            return ToolResult(
                output=f"Prepare failed: code={resp.code} msg={resp.msg}",
                is_error=True,
            )
        upload_id = getattr(getattr(resp, "data", None), "upload_id", "")
        block_num = (file_size + block_size - 1) // block_size

        # 2. upload parts
        with open(path, "rb") as f:
            for i in range(block_num):
                chunk = f.read(block_size)
                part_body = {
                    "upload_id": upload_id,
                    "seq": i,
                    "size": len(chunk),
                    "file": chunk,
                }
                req = UploadPartFileRequest.builder().request_body(part_body).build()  # pyright: ignore[reportArgumentType]
                resp = client.drive.v1.file.upload_part(req)
                if not resp.success():
                    return ToolResult(
                        output=f"Part {i} failed: code={resp.code} msg={resp.msg}",
                        is_error=True,
                    )

        # 3. finish
        finish_body = {
            "upload_id": upload_id,
            "block_num": block_num,
        }
        req = UploadFinishFileRequest.builder().request_body(finish_body).build()  # pyright: ignore[reportArgumentType]
        resp = client.drive.v1.file.upload_finish(req)
        if not resp.success():
            return ToolResult(
                output=f"Finish failed: code={resp.code} msg={resp.msg}",
                is_error=True,
            )
        data = getattr(resp, "data", None)
        token = getattr(data, "file_token", "?") if data else "?"
        return ToolResult(output=f"Uploaded (chunked): {name} token={token}")


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


class FeishuDriveDownloadTool(BaseTool[FeishuDriveDownloadInput]):
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
            from lark_oapi.api.drive.v1 import (
                DownloadFileRequest,
            )
        except ImportError:
            return ToolResult(output="lark_oapi drive API not available", is_error=True)

        req = DownloadFileRequest.builder().file_token(arguments.file_token).file_type(arguments.file_type).build()  # pyright: ignore[reportAttributeAccessIssue]
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


class FeishuDriveMkdirInput(BaseModel):
    """飞书云盘创建文件夹工具输入

    Attributes:
        name: 文件夹名称
        folder_token: 父文件夹 token（可选，默认根目录）
    """

    name: str = Field(..., description="Folder name")
    folder_token: str = Field("", description="Parent folder token (empty for root)")


class FeishuDriveMkdirTool(BaseTool[FeishuDriveMkdirInput]):
    """在飞书云盘创建文件夹"""

    name = "feishu_drive_mkdir"
    description = "Create a new folder in Feishu/Lark Drive."
    input_model = FeishuDriveMkdirInput

    def __init__(self, channel_config: "FeishuChannelConfig") -> None:
        """初始化

        Args:
            channel_config: 飞书渠道配置
        """
        self._cfg = channel_config

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        """执行创建文件夹

        Args:
            arguments: 输入参数（FeishuDriveMkdirInput）
            context: 执行上下文

        Returns:
            ToolResult: 创建结果（含 token 和 url）或错误
        """
        assert isinstance(arguments, FeishuDriveMkdirInput)
        client = build_lark_client(self._cfg)
        try:
            from lark_oapi.api.drive.v1 import (  # pyright: ignore[reportAttributeAccessIssue]
                CreateFolderRequest,  # pyright: ignore[reportAttributeAccessIssue]
            )
        except ImportError:
            return ToolResult(output="lark_oapi drive API not available", is_error=True)

        body = {"name": arguments.name, "folder_token": arguments.folder_token}
        req = CreateFolderRequest.builder().request_body(body).build()
        resp = client.drive.v1.folder.create(req)
        if not resp.success():
            return ToolResult(
                output=f"Mkdir failed: code={resp.code} msg={resp.msg}",
                is_error=True,
            )
        data = getattr(resp, "data", None)
        token = getattr(data, "token", "?") if data else "?"
        url = getattr(data, "url", "") if data else ""
        return ToolResult(output=f"Created folder: {arguments.name} token={token} url={url}")


class FeishuDriveDeleteInput(BaseModel):
    """飞书云盘删除工具输入

    Attributes:
        file_token: 文件 token
        file_type: 文件类型（file/docx/sheet 等）
    """

    file_token: str = Field(..., description="File token to delete")
    file_type: str = Field("file", description="File type (file/docx/sheet)")


class FeishuDriveDeleteTool(BaseTool[FeishuDriveDeleteInput]):
    """删除飞书云盘文件到回收站"""

    name = "feishu_drive_delete"
    description = "Delete a Feishu/Lark Drive file (move to trash)."
    input_model = FeishuDriveDeleteInput

    def __init__(self, channel_config: "FeishuChannelConfig") -> None:
        """初始化

        Args:
            channel_config: 飞书渠道配置
        """
        self._cfg = channel_config

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        """执行文件删除

        Args:
            arguments: 输入参数（FeishuDriveDeleteInput）
            context: 执行上下文

        Returns:
            ToolResult: 删除结果或错误
        """
        assert isinstance(arguments, FeishuDriveDeleteInput)
        client = build_lark_client(self._cfg)
        try:
            from lark_oapi.api.drive.v1 import (
                DeleteFileRequest,
            )
        except ImportError:
            return ToolResult(output="lark_oapi drive API not available", is_error=True)

        req = DeleteFileRequest.builder().file_token(arguments.file_token).type(arguments.file_type).build()
        resp = client.drive.v1.file.delete(req)
        if not resp.success():
            return ToolResult(
                output=f"Delete failed: code={resp.code} msg={resp.msg}",
                is_error=True,
            )
        return ToolResult(output=f"Deleted: {arguments.file_token}")
