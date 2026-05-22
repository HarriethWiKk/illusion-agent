"""Tests for MediaBlock content block."""
from __future__ import annotations

import pytest

from illusion.engine.messages import (
    ContentBlock,
    MediaBlock,
    TextBlock,
    serialize_content_block,
)


def test_media_block_is_valid_content_block():
    block = MediaBlock(
        file_path="/tmp/img.png",
        media_type="image/png",
        category="image",
        data="iVBOR...",
    )
    assert block.type == "media"
    assert block.category == "image"


def test_media_block_discriminator():
    block = MediaBlock(
        file_path="/tmp/img.png",
        media_type="image/png",
        category="image",
        data="abc",
    )
    assert isinstance(block, MediaBlock)


def test_serialize_media_block_anthropic_image():
    block = MediaBlock(
        file_path="/tmp/img.png",
        media_type="image/png",
        category="image",
        data="abc123",
    )
    result = serialize_content_block(block, provider_type="anthropic")
    assert result["type"] == "image"
    assert result["source"]["type"] == "base64"
    assert result["source"]["media_type"] == "image/png"
    assert result["source"]["data"] == "abc123"


def test_serialize_media_block_openai_image():
    block = MediaBlock(
        file_path="/tmp/img.png",
        media_type="image/png",
        category="image",
        data="abc123",
    )
    result = serialize_content_block(block, provider_type="openai_compat")
    assert result["type"] == "image_url"
    assert result["image_url"]["url"].startswith("data:image/png;base64,abc123")


def test_serialize_media_block_codex_image():
    block = MediaBlock(
        file_path="/tmp/img.png",
        media_type="image/png",
        category="image",
        data="abc123",
    )
    result = serialize_content_block(block, provider_type="openai_codex")
    assert result["type"] == "input_image"
    assert result["image_url"].startswith("data:image/png;base64,abc123")


def test_serialize_media_block_unsupported_video():
    block = MediaBlock(
        file_path="/tmp/vid.mp4",
        media_type="video/mp4",
        category="video",
        data="abc123",
        metadata={"size": 1024},
    )
    result = serialize_content_block(block, provider_type="anthropic")
    assert result["type"] == "text"
    assert "video" in result["text"].lower()
    assert "does not support" in result["text"].lower()


def test_serialize_media_block_openai_audio():
    block = MediaBlock(
        file_path="/tmp/audio.mp3",
        media_type="audio/mpeg",
        category="audio",
        data="abc123",
    )
    result = serialize_content_block(block, provider_type="openai_compat")
    assert result["type"] == "input_audio"
    assert result["input_audio"]["data"] == "abc123"
    assert result["input_audio"]["format"] == "mp3"


def test_serialize_media_block_unsupported_audio_anthropic():
    block = MediaBlock(
        file_path="/tmp/audio.mp3",
        media_type="audio/mpeg",
        category="audio",
        data="abc123",
    )
    result = serialize_content_block(block, provider_type="anthropic")
    assert result["type"] == "text"
    assert "audio" in result["text"].lower()
