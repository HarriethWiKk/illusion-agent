"""QQ Bot REST API 客户端
========================

封装 QQ 开放平台 API v2 的 HTTP 调用：token 管理、消息发送、文件上传。

所有函数接受 aiohttp.ClientSession，由调用方管理生命周期。

参考文档：https://bot.q.qq.com/wiki/develop/api-v2/
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

# ── API 端点 ──────────────────────────────────────────────────

API_BASE = "https://api.sgroup.qq.com"
TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
GATEWAY_URL = f"{API_BASE}/gateway"

# ── 消息类型 ──────────────────────────────────────────────────

MSG_TYPE_TEXT = 0
MSG_TYPE_MARKDOWN = 2
MSG_TYPE_MEDIA = 7
MSG_TYPE_INPUT_NOTIFY = 6

# ── 媒体类型 ──────────────────────────────────────────────────

MEDIA_TYPE_IMAGE = 1
MEDIA_TYPE_VIDEO = 2
MEDIA_TYPE_VOICE = 3
MEDIA_TYPE_FILE = 4

# ── 消息限制 ──────────────────────────────────────────────────

MAX_MESSAGE_LENGTH = 4000
DEDUP_WINDOW_SECONDS = 300
DEDUP_MAX_SIZE = 1000

# ── 重连参数 ──────────────────────────────────────────────────

RECONNECT_BACKOFF = [2, 5, 10, 30, 60]
MAX_RECONNECT_ATTEMPTS = 100
RATE_LIMIT_DELAY = 60

# ── Token 管理 ────────────────────────────────────────────────

# 全局 token 缓存（按 app_id 隔离）
_token_cache: dict[str, dict[str, Any]] = {}


async def ensure_token(
    session: aiohttp.ClientSession,
    app_id: str,
    client_secret: str,
) -> str:
    """获取或刷新 app_access_token

    Token 有效期 7200s，过期前 300s 自动刷新。

    Args:
        session: HTTP 会话
        app_id: 应用 ID
        client_secret: 应用密钥

    Returns:
        str: 有效的 access_token
    """
    cached = _token_cache.get(app_id)
    if cached and cached["expires_at"] > time.monotonic() + 300:
        return cached["token"]

    payload = {"appId": app_id, "clientSecret": client_secret}
    async with session.post(TOKEN_URL, json=payload) as resp:
        resp.raise_for_status()
        data = await resp.json()

    token = data["access_token"]
    expires_in = int(data.get("expires_in", 7200))
    _token_cache[app_id] = {
        "token": token,
        "expires_at": time.monotonic() + expires_in,
    }
    logger.info("QQ token 已刷新，有效期 %ds", expires_in)
    return token


# ── 网关 ──────────────────────────────────────────────────────

async def get_gateway_url(
    session: aiohttp.ClientSession,
    token: str,
) -> str:
    """获取 WebSocket 网关地址

    Args:
        session: HTTP 会话
        token: access_token

    Returns:
        str: wss:// 网关 URL
    """
    headers = {"Authorization": f"QQBot {token}"}
    async with session.get(GATEWAY_URL, headers=headers) as resp:
        resp.raise_for_status()
        data = await resp.json()
    url = data["url"]
    logger.info("QQ 网关地址: %s", url)
    return url


# ── 消息发送 ──────────────────────────────────────────────────

async def send_c2c_message(
    session: aiohttp.ClientSession,
    token: str,
    openid: str,
    content: str,
    msg_id: str,
) -> dict[str, Any]:
    """发送 C2C 私聊消息

    Args:
        session: HTTP 会话
        token: access_token
        openid: 用户 openid
        content: 消息内容
        msg_id: 引用的消息 ID（用于回复）

    Returns:
        dict: API 响应
    """
    url = f"{API_BASE}/v2/users/{openid}/messages"
    headers = {"Authorization": f"QQBot {token}"}
    body: dict[str, Any] = {
        "content": content[:MAX_MESSAGE_LENGTH],
        "msg_type": MSG_TYPE_TEXT,
        "msg_id": msg_id,
    }
    async with session.post(url, headers=headers, json=body) as resp:
        resp.raise_for_status()
        return await resp.json()


async def send_group_message(
    session: aiohttp.ClientSession,
    token: str,
    group_openid: str,
    content: str,
    msg_id: str,
) -> dict[str, Any]:
    """发送群聊消息

    Args:
        session: HTTP 会话
        token: access_token
        group_openid: 群 openid
        content: 消息内容
        msg_id: 引用的消息 ID（用于回复）

    Returns:
        dict: API 响应
    """
    url = f"{API_BASE}/v2/groups/{group_openid}/messages"
    headers = {"Authorization": f"QQBot {token}"}
    body: dict[str, Any] = {
        "content": content[:MAX_MESSAGE_LENGTH],
        "msg_type": MSG_TYPE_TEXT,
        "msg_id": msg_id,
    }
    async with session.post(url, headers=headers, json=body) as resp:
        resp.raise_for_status()
        return await resp.json()


# ── 打字状态 ──────────────────────────────────────────────────

async def send_typing(
    session: aiohttp.ClientSession,
    token: str,
    msg_id: str,
) -> None:
    """发送 C2C 打字状态指示

    QQ API v2 的打字状态通过 input_notify 消息类型实现。
    具体端点取决于 API 版本。

    Args:
        session: HTTP 会话（保留以备后续使用）
        token: access_token（保留以备后续使用）
        msg_id: 最近一条入站消息 ID（保留以备后续使用）
    """
    # TODO: QQ API v2 打字状态端点待确认
    logger.debug("QQ 打字状态指示（占位）")


# ── 文件上传（三步分片） ──────────────────────────────────────

async def upload_file(
    session: aiohttp.ClientSession,
    token: str,
    target_id: str,
    file_path: str,
    *,
    is_group: bool = False,
) -> dict[str, Any]:
    """三步分片上传文件

    1. upload_prepare → 获取 upload_id + presigned URLs
    2. PUT 每个分片到 presigned URL
    3. POST files → 获取 file_info

    Args:
        session: HTTP 会话
        token: access_token
        target_id: openid 或 group_openid
        file_path: 本地文件路径
        is_group: 是否群聊目标

    Returns:
        dict: file_info
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    file_size = path.stat().st_size
    file_sha = _file_sha256(path)

    # 确定上传目标路径前缀
    target_type = "groups" if is_group else "users"
    base_url = f"{API_BASE}/v2/{target_type}/{target_id}"
    headers = {"Authorization": f"QQBot {token}"}

    # Step 1: upload_prepare
    prepare_body = {
        "file_name": path.name,
        "file_size": file_size,
        "file_sha": file_sha,
    }
    async with session.post(
        f"{base_url}/files/upload_prepare",
        headers=headers, json=prepare_body,
    ) as resp:
        resp.raise_for_status()
        prepare_data = await resp.json()

    upload_id = prepare_data["upload_id"]
    part_urls = prepare_data.get("part_urls", [])

    # Step 2: 上传每个分片
    file_bytes = path.read_bytes()
    part_size = prepare_data.get("part_size", file_size)
    for i, part_url in enumerate(part_urls):
        start = i * part_size
        end = min(start + part_size, file_size)
        part_data = file_bytes[start:end]
        async with session.put(part_url, data=part_data) as resp:
            resp.raise_for_status()

    # Step 3: 完成上传
    complete_body = {"upload_id": upload_id}
    async with session.post(
        f"{base_url}/files",
        headers=headers, json=complete_body,
    ) as resp:
        resp.raise_for_status()
        return await resp.json()


def _file_sha256(path: Path) -> str:
    """计算文件 SHA256"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ── 文本分片 ──────────────────────────────────────────────────

def split_text(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """超长文本按段落边界分片

    Args:
        text: 原始文本
        max_length: 每片最大长度

    Returns:
        list[str]: 分片列表
    """
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        # 在 max_length 范围内找最后一个段落分隔
        cut = max_length
        for sep in ["\n\n", "\n", "。", ".", " "]:
            pos = text.rfind(sep, 0, max_length)
            if pos > max_length // 2:  # 至少从中间切
                cut = pos + len(sep)
                break

        chunks.append(text[:cut])
        text = text[cut:]

    return chunks
