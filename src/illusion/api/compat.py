"""
API 兼容辅助模块
================

本模块提供不同模型供应商之间的兼容处理辅助函数。

主要功能：
    - 解析非标准工具参数字符串
    - 清理模型输出中的工具调用残留标签
    - 提取并拆分 `<think>` 思考内容
    - 合并去重多来源推理文本
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

_THINK_BLOCK_RE = re.compile(r"<(?:think|thought)\b[^>]*>([\s\S]*?)</(?:think|thought)\b[^>]*>", re.IGNORECASE)
_THINK_OPEN_TAG_RE = re.compile(r"<(?:think|thought)\b[^>]*>", re.IGNORECASE)
_THINK_CLOSE_TAG_RE = re.compile(r"</(?:think|thought)\b[^>]*>", re.IGNORECASE)
_JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*([\s\S]*?)\s*```\s*$", re.IGNORECASE)
_DSML_TOOL_CALL_PREFIX_RE = re.compile(
    r"<\s*[|｜]\s*DSML\s*[|｜]\s*tool_calls[^\n>]*>?",
    re.IGNORECASE,
)
_TOOL_CALL_XML_BLOCK_RE = re.compile(r"<tool_call\b[^>]*>[\s\S]*?</tool_call\b[^>]*>", re.IGNORECASE)
_TOOL_CALL_XML_TAG_RE = re.compile(r"</?(?:tool_call|arg_key|arg_value)\b[^>]*>", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_tool_artifacts(raw: str) -> str:
    """清理模型输出中的工具调用残留标签。"""
    if not raw:
        return ""
    return (
        raw.replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
        .replace("\u0000", "")
    ).replace("\t", "    ")


def strip_tool_call_artifacts(raw: str) -> str:
    """移除 DeepSeek/类 XML 工具调用残留，避免污染用户可见文本。"""
    if not raw:
        return ""
    cleaned = _DSML_TOOL_CALL_PREFIX_RE.sub("", raw)
    cleaned = _TOOL_CALL_XML_BLOCK_RE.sub("", cleaned)
    cleaned = _TOOL_CALL_XML_TAG_RE.sub("", cleaned)
    return cleaned


def split_thinking_from_text(raw: str) -> tuple[str, str]:
    """从文本中提取 `<think>` 内容，并返回正文与思考文本。"""
    if not raw:
        return "", ""
    source = strip_tool_call_artifacts(sanitize_tool_artifacts(raw))
    thinking_parts = [m.group(1).strip() for m in _THINK_BLOCK_RE.finditer(source) if m.group(1).strip()]
    without_full_blocks = _THINK_BLOCK_RE.sub("", source)

    dangling_open = _THINK_OPEN_TAG_RE.search(without_full_blocks)
    if dangling_open:
        tail = without_full_blocks[dangling_open.end():].strip()
        if tail:
            thinking_parts.append(tail)
        without_full_blocks = without_full_blocks[:dangling_open.start()]

    plain = _THINK_OPEN_TAG_RE.sub("", without_full_blocks)
    plain = _THINK_CLOSE_TAG_RE.sub("", plain).strip()
    thinking = merge_reasoning_text(*thinking_parts)
    return plain, thinking


def parse_tool_arguments(raw: Any) -> dict[str, Any]:
    """将工具参数解析为字典，兼容常见非标准格式。"""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}

    text = raw.strip()
    if not text:
        return {}

    fenced = _JSON_FENCE_RE.match(text)
    if fenced:
        text = fenced.group(1).strip()

    parsed = _parse_json_dict(text)
    if parsed:
        return parsed

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        parsed = _parse_json_dict(text[first_brace : last_brace + 1].strip())
        if parsed:
            return parsed

    try:
        literal = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return {}
    return literal if isinstance(literal, dict) else {}


def merge_reasoning_text(*parts: str) -> str:
    """合并多个推理文本片段并去重。"""
    merged: list[str] = []
    for part in parts:
        cleaned = strip_tool_call_artifacts(sanitize_tool_artifacts(part)).strip()
        if not cleaned:
            continue
        candidate = _normalize_compare_text(cleaned)
        if not candidate:
            continue
        normalized_existing = [_normalize_compare_text(value) for value in merged]
        if any(existing == candidate or candidate in existing for existing in normalized_existing):
            continue
        merged = [value for value in merged if _normalize_compare_text(value) not in candidate]
        merged.append(cleaned)
    return "\n\n".join(merged).strip()


def _parse_json_dict(text: str) -> dict[str, Any]:
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _normalize_compare_text(raw: str) -> str:
    return _WHITESPACE_RE.sub(" ", raw).strip()

