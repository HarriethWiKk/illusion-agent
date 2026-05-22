"""Tests for FileReadTool media file handling."""
from __future__ import annotations

from pathlib import Path

import pytest

from illusion.tools.file_read_tool import FileReadTool, FileReadToolInput
from illusion.tools.base import ToolExecutionContext


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
async def test_read_audio_mp3(tmp_path: Path):
    context = ToolExecutionContext(cwd=tmp_path)
    audio_path = tmp_path / "sound.mp3"
    audio_path.write_bytes(b"\xff\xfb" + b"\x00" * 100)
    result = await FileReadTool().execute(
        FileReadToolInput(path=str(audio_path)),
        context,
    )
    assert result.is_error is False
    assert result.metadata.get("media_category") == "audio"
    assert result.metadata.get("media_type") == "audio/mpeg"


@pytest.mark.asyncio
async def test_read_video_mp4(tmp_path: Path):
    context = ToolExecutionContext(cwd=tmp_path)
    vid_path = tmp_path / "clip.mp4"
    vid_path.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"\x00" * 100)
    result = await FileReadTool().execute(
        FileReadToolInput(path=str(vid_path)),
        context,
    )
    assert result.is_error is False
    assert result.metadata.get("media_category") == "video"
    assert result.metadata.get("media_type") == "video/mp4"


@pytest.mark.asyncio
async def test_read_media_oversized(tmp_path: Path):
    context = ToolExecutionContext(cwd=tmp_path)
    img_path = tmp_path / "big.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (21 * 1024 * 1024))
    result = await FileReadTool().execute(
        FileReadToolInput(path=str(img_path)),
        context,
    )
    assert result.is_error is True
    assert "too large" in result.output.lower() or "exceeds" in result.output.lower()


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
