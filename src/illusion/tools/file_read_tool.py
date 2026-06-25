"""
文件读取工具
===========

本模块提供读取本地文件系统文件的功能，支持文本文件和图片文件。

主要组件：
    - FileReadTool: 读取文本文件和图片文件的工具

使用示例：
    >>> from illusion.tools import FileReadTool
    >>> tool = FileReadTool()
"""

from __future__ import annotations

from typing import Any

import base64
import json
import mimetypes
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult

# 图片文件扩展名集合
_IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
})

# 图片文件大小限制（字节）
_IMAGE_SIZE_LIMIT: int = 20 * 1024 * 1024  # 20 MB


def _is_image_file(path: Path) -> bool:
    """检测文件是否为图片文件。"""
    return path.suffix.lower() in _IMAGE_EXTENSIONS


def _get_media_type(path: Path) -> str:
    """获取文件的 MIME 类型。"""
    media_type, _ = mimetypes.guess_type(str(path))
    if media_type:
        return media_type
    fallback = {
        ".svg": "image/svg+xml",
    }
    return fallback.get(path.suffix.lower(), "application/octet-stream")


class FileReadToolInput(BaseModel):
    """文件读取参数。

    属性：
        file_path: 要读取的文件路径
        offset: 起始行号（从 0 开始）
        limit: 返回的行数限制

    兼容旧参数名：path 也可传入，会自动映射。
    """

    file_path: str = Field(description="Path of the file to read")
    offset: int = Field(default=0, ge=0, description="Zero-based starting line")
    limit: int = Field(default=2000, ge=1, le=2000, description="Number of lines to return")

    @model_validator(mode="before")
    @classmethod
    def _normalize_fields(cls, values: dict[str, Any]) -> dict[str, Any]:
        """将旧参数名映射到新参数名，确保向后兼容。"""
        if "path" in values and "file_path" not in values:
            values["file_path"] = values.pop("path")
        return values


class FileReadTool(BaseTool[FileReadToolInput]):
    """读取文本文件和图片文件。

    支持图片（PNG, JPG, GIF, WebP 等），通过 base64 编码传递给多模态模型。
    """

    name = "read_file"
    description = """Reads a file from the local filesystem. You can access any file directly by using this tool.
Assume this tool is able to read all files on the machine. If the User provides a file_path to a file assume that file_path is valid. It is okay to read a file that does not exist; an error will be returned.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- By default, it reads up to 2000 lines starting from the beginning of the file
- You can optionally specify a line offset and limit (especially handy for long files), but it's recommended to read the whole file by not providing these parameters
- Results are returned using cat -n format, with line numbers starting at 1
- This tool allows Illusion Code to read images (eg PNG, JPG, etc). When reading an image file the contents are presented visually as Illusion Code is a multimodal LLM.
- This tool can read Jupyter notebooks (.ipynb files) and returns all cells with their outputs, combining code, text, and visualizations.
- This tool can only read files, not directories. To read a directory, use an ls command via the Bash tool.
- You will regularly be asked to read screenshots. If the user provides a file_path to a screenshot, ALWAYS use this tool to view the file at the path. This tool will work with all temporary file paths.
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
        path = _resolve_path(context.cwd, arguments.file_path)
        # 检查文件是否存在
        if not path.exists():
            return ToolResult(output=f"File not found: {path}", is_error=True)
        # 检查是否为目录
        if path.is_dir():
            return ToolResult(output=f"Cannot read directory: {path}", is_error=True)

        # 检测是否为 Jupyter notebook
        if path.suffix.lower() == ".ipynb":
            return self._read_notebook_file(path, arguments)

        # 检测是否为图片文件
        if _is_image_file(path):
            return self._read_image_file(path)

        # 读取文本文件
        return self._read_text_file(path, arguments)

    def _read_image_file(self, path: Path) -> ToolResult:
        """读取图片文件并返回 base64 编码数据。"""
        raw = path.read_bytes()
        file_size = len(raw)

        # 检查文件大小限制
        if file_size > _IMAGE_SIZE_LIMIT:
            limit_mb = _IMAGE_SIZE_LIMIT // (1024 * 1024)
            return ToolResult(
                output=f"Image file too large: {file_size} bytes exceeds {limit_mb} MB limit",
                is_error=True,
            )

        media_type = _get_media_type(path)
        encoded = base64.b64encode(raw).decode("ascii")

        # 生成输出描述
        size_str = _human_size(file_size)
        output = f"[image file: {path} ({size_str}, {media_type})]"

        return ToolResult(
            output=output,
            metadata={
                "media_category": "image",
                "media_type": media_type,
                "media_data": encoded,
                "media_path": str(path),
                "media_size": file_size,
            },
        )

    def _read_notebook_file(self, path: Path, arguments: FileReadToolInput) -> ToolResult:
        """读取 Jupyter notebook 文件，解析所有单元格及其输出。"""
        try:
            raw = path.read_text(encoding="utf-8")
            nb = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return ToolResult(output=f"Failed to parse notebook {path}: {e}", is_error=True)

        cells = nb.get("cells", [])
        if not cells:
            return ToolResult(output=f"System reminder: The notebook at {path} exists but has no cells.")

        # 应用 offset/limit 到单元格级别
        selected_cells = cells[arguments.offset : arguments.offset + arguments.limit]
        if not selected_cells:
            return ToolResult(
                output=f"System reminder: No cells in selected range (offset={arguments.offset}, limit={arguments.limit}) for {path}"
            )

        output_parts: list[str] = []
        for cell in selected_cells:
            idx = cells.index(cell)
            cell_type = cell.get("cell_type", "code")
            source = "".join(cell.get("source", ""))
            if isinstance(source, list):
                source = "".join(source)

            if cell_type == "markdown":
                output_parts.append(f"## Cell {idx} (markdown)\n{source}")
            elif cell_type == "code":
                exec_count = cell.get("execution_count")
                status = f"executed, count={exec_count}" if exec_count is not None else "not executed"
                output_parts.append(f"## Cell {idx} (code) [{status}]")
                if source.strip():
                    output_parts.append(source)
                else:
                    output_parts.append("(empty cell)")

                # 格式化输出
                outputs = cell.get("outputs", [])
                if outputs:
                    output_parts.append("\n**Outputs:**")
                    for out in outputs:
                        out_type = out.get("output_type", "")
                        if out_type == "stream":
                            text = "".join(out.get("text", ""))
                            if isinstance(text, list):
                                text = "".join(text)
                            name = out.get("name", "stdout")
                            output_parts.append(f"[{name}]:\n{text}")
                        elif out_type == "execute_result":
                            data = out.get("data", {})
                            text = data.get("text/plain", "")
                            if isinstance(text, list):
                                text = "".join(text)
                            output_parts.append(f"[result]: {text}")
                        elif out_type == "error":
                            ename = out.get("ename", "Error")
                            evalue = out.get("evalue", "")
                            traceback = out.get("traceback", [])
                            if isinstance(traceback, list):
                                traceback_text = "\n".join(traceback)
                            else:
                                traceback_text = str(traceback)
                            output_parts.append(f"[error]: {ename}: {evalue}\n{traceback_text}")
                        elif out_type == "display_data":
                            data = out.get("data", {})
                            text = data.get("text/plain", "")
                            if isinstance(text, list):
                                text = "".join(text)
                            if text:
                                output_parts.append(f"[display]: {text}")
                            if "image/png" in data:
                                output_parts.append("[display]: <image/png>")
                elif exec_count is not None:
                    output_parts.append("\n**Outputs:** (none)")
            else:
                source = "".join(cell.get("source", ""))
                if isinstance(source, list):
                    source = "".join(source)
                output_parts.append(f"## Cell {idx} ({cell_type})\n{source}")

            output_parts.append("")  # 单元格间空行

        # 注册文件已被读取
        from illusion.tools.file_edit_tool import mark_file_read
        mark_file_read(str(path))

        return ToolResult(output="\n".join(output_parts).strip())

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
            return ToolResult(
                output=f"System reminder: The file at {path} exists but has empty contents."
            )

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
