"""Tests for FileReadTool image file handling."""
from __future__ import annotations

from pathlib import Path

import pytest

from illusion.tools.base import ToolExecutionContext
from illusion.tools.file_read_tool import FileReadTool, FileReadToolInput


@pytest.mark.asyncio
async def test_read_image_png(tmp_path: Path):
    context = ToolExecutionContext(cwd=tmp_path)
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    result = await FileReadTool().execute(
        FileReadToolInput(path=str(img_path)),
        context,
    )
    assert result.is_error is False
    assert result.metadata.get("media_category") == "image"
    assert result.metadata.get("media_type") == "image/png"
    assert "media_data" in result.metadata
    assert "media_path" in result.metadata


@pytest.mark.asyncio
async def test_read_image_jpg(tmp_path: Path):
    context = ToolExecutionContext(cwd=tmp_path)
    img_path = tmp_path / "photo.jpg"
    img_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
    result = await FileReadTool().execute(
        FileReadToolInput(path=str(img_path)),
        context,
    )
    assert result.is_error is False
    assert result.metadata.get("media_category") == "image"
    assert result.metadata.get("media_type") == "image/jpeg"


@pytest.mark.asyncio
async def test_read_image_oversized(tmp_path: Path):
    context = ToolExecutionContext(cwd=tmp_path)
    img_path = tmp_path / "big.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (21 * 1024 * 1024))
    result = await FileReadTool().execute(
        FileReadToolInput(path=str(img_path)),
        context,
    )
    assert result.is_error is True
    assert "too large" in result.output.lower()


@pytest.mark.asyncio
async def test_read_text_file_unchanged(tmp_path: Path):
    context = ToolExecutionContext(cwd=tmp_path)
    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("hello world\n", encoding="utf-8")
    result = await FileReadTool().execute(
        FileReadToolInput(path=str(txt_path)),
        context,
    )
    assert result.is_error is False
    assert "hello world" in result.output
    assert not result.metadata.get("media_category")


@pytest.mark.asyncio
async def test_video_audio_not_treated_as_media(tmp_path: Path):
    """视频和音频文件应走普通二进制文件路径，返回错误。"""
    context = ToolExecutionContext(cwd=tmp_path)
    mp4_path = tmp_path / "video.mp4"
    mp4_path.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"\x00" * 100)
    result = await FileReadTool().execute(
        FileReadToolInput(path=str(mp4_path)),
        context,
    )
    assert result.is_error is True
    assert "binary" in result.output.lower() or "cannot be read" in result.output.lower()
