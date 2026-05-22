"""
文件读取工具
===========

本模块提供读取本地文件系统文件的功能，支持文本文件和媒体文件（图片/视频/音频）。

主要组件：
    - FileReadTool: 读取文本文件和媒体文件的工具

使用示例：
    >>> from illusion.tools import FileReadTool
    >>> tool = FileReadTool()
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from pydantic import BaseModel, Field

from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult

# 媒体文件扩展名到分类的映射
_MEDIA_EXTENSIONS: dict[str, str] = {
    # 图片
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".gif": "image", ".webp": "image", ".bmp": "image", ".svg": "image",
    # 视频
    ".mp4": "video", ".avi": "video", ".mov": "video",
    ".mkv": "video", ".webm": "video",
    # 音频
    ".mp3": "audio", ".wav": "audio", ".ogg": "audio",
    ".flac": "audio", ".aac": "audio", ".m4a": "audio",
}

# 各类别的文件大小限制（字节）
_SIZE_LIMITS: dict[str, int] = {
    "image": 20 * 1024 * 1024,   # 20 MB
    "video": 50 * 1024 * 1024,   # 50 MB
    "audio": 25 * 1024 * 1024,   # 25 MB
}


def _detect_media_category(path: Path) -> str | None:
    """检测文件是否为媒体文件，返回分类或 None。"""
    return _MEDIA_EXTENSIONS.get(path.suffix.lower())


def _get_media_type(path: Path) -> str:
    """获取文件的 MIME 类型。"""
    media_type, _ = mimetypes.guess_type(str(path))
    if media_type:
        return media_type
    fallback = {
        ".svg": "image/svg+xml",
        ".webm": "video/webm",
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
    }
    return fallback.get(path.suffix.lower(), "application/octet-stream")


class FileReadToolInput(BaseModel):
    """文件读取参数。

    属性：
        path: 要读取的文件路径
        offset: 起始行号（从 0 开始）
        limit: 返回的行数限制
    """

    path: str = Field(description="Path of the file to read")
    offset: int = Field(default=0, ge=0, description="Zero-based starting line")
    limit: int = Field(default=200, ge=1, le=2000, description="Number of lines to return")


class FileReadTool(BaseTool):
    """读取文本文件和媒体文件。

    支持图片（PNG, JPG, GIF, WebP 等）、音频（MP3, WAV 等）和视频（MP4 等）。
    媒体文件通过 base64 编码后传递给多模态模型。
    """

    name = "read_file"
    description = """Reads a file from the local filesystem. You can access any file directly by using this tool.
Assume this tool is able to read all files on the machine. If the User provides a path to a file assume that path is valid. It is okay to read a file that does not exist; an error will be returned.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- By default, it reads up to 2000 lines starting from the beginning of the file
- You can optionally specify a line offset and limit (especially handy for long files), but it's recommended to read the whole file by not providing these parameters
- Results are returned using cat -n format, with line numbers starting at 1
- This tool allows Illusion Code to read images (eg PNG, JPG, etc). When reading an image file the contents are presented visually as Illusion Code is a multimodal LLM.
- This tool can read PDF files (.pdf). For large PDFs (more than 10 pages), you MUST provide the pages parameter to read specific page ranges (e.g., pages: "1-5"). Reading a large PDF without the pages parameter will fail. Maximum 20 pages per request.
- This tool can read Jupyter notebooks (.ipynb files) and returns all cells with their outputs, combining code, text, and visualizations.
- This tool can read audio files (MP3, WAV, OGG, FLAC, AAC, M4A) and video files (MP4, AVI, MOV, MKV, WebM) for multimodal models that support them.
- This tool can only read files, not directories. To read a directory, use an ls command via the Bash tool.
- You will regularly be asked to read screenshots. If the user provides a path to a screenshot, ALWAYS use this tool to view the file at the path. This tool will work with all temporary file paths.
- If you read a file that exists but has empty contents you will receive a system reminder warning in place of file contents."""
    input_model = FileReadToolInput

    def is_read_only(self, arguments: FileReadToolInput) -> bool:
        del arguments
        return True

    async def execute(
        self,
        arguments: FileReadToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        # 解析文件路径
        path = _resolve_path(context.cwd, arguments.path)
        # 检查文件是否存在
        if not path.exists():
            return ToolResult(output=f"File not found: {path}", is_error=True)
        # 检查是否为目录
        if path.is_dir():
            return ToolResult(output=f"Cannot read directory: {path}", is_error=True)

        # 检测是否为媒体文件
        category = _detect_media_category(path)
        if category is not None:
            return self._read_media_file(path, category)

        # 读取文本文件
        return self._read_text_file(path, arguments)

    def _read_media_file(self, path: Path, category: str) -> ToolResult:
        """读取媒体文件并返回 base64 编码数据。"""
        raw = path.read_bytes()
        file_size = len(raw)

        # 检查文件大小限制
        size_limit = _SIZE_LIMITS.get(category, 20 * 1024 * 1024)
        if file_size > size_limit:
            limit_mb = size_limit // (1024 * 1024)
            return ToolResult(
                output=f"File too large for {category}: {file_size} bytes exceeds {limit_mb} MB limit",
                is_error=True,
            )

        media_type = _get_media_type(path)
        encoded = base64.b64encode(raw).decode("ascii")

        # 生成输出描述
        size_str = _human_size(file_size)
        output = f"[{category} file: {path} ({size_str}, {media_type})]"

        return ToolResult(
            output=output,
            metadata={
                "media_category": category,
                "media_type": media_type,
                "media_data": encoded,
                "media_path": str(path),
                "media_size": file_size,
            },
        )

    def _read_text_file(self, path: Path, arguments: FileReadToolInput) -> ToolResult:
        """读取文本文件。"""
        raw = path.read_bytes()
        if b"\x00" in raw:
            return ToolResult(output=f"Binary file cannot be read as text: {path}", is_error=True)

        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        selected = lines[arguments.offset : arguments.offset + arguments.limit]
        numbered = [
            f"{arguments.offset + index + 1:>6}\t{line}"
            for index, line in enumerate(selected)
        ]
        if not numbered:
            return ToolResult(output=f"(no content in selected range for {path})")

        # 注册文件已被读取（用于读后编辑强制检查）
        from illusion.tools.file_edit_tool import mark_file_read
        mark_file_read(str(path))

        return ToolResult(output="\n".join(numbered))


def _human_size(size: int) -> str:
    """将字节数转为人类可读的大小字符串。"""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _resolve_path(base: Path, candidate: str) -> Path:
    """解析相对路径为绝对路径。

    参数：
        base: 基础目录
        candidate: 候选路径（可能是相对路径）

    返回：
        解析后的绝对路径
    """
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()
