"""QQ Bot REST API 客户端
========================

封装 QQ 开放平台 API v2 的 HTTP 调用：token 管理、消息发送、文件上传。

所有函数接受 aiohttp.ClientSession，由调用方管理生命周期。

参考文档：https://bot.q.qq.com/wiki/develop/api-v2/
"""
from __future__ import annotations

import hashlib
import logging
import re
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
    *,
    markdown: bool = False,
) -> dict[str, Any]:
    """发送 C2C 私聊消息

    Args:
        session: HTTP 会话
        token: access_token
        openid: 用户 openid
        content: 消息内容
        msg_id: 引用的消息 ID（用于回复）
        markdown: 是否使用 markdown 信封（msg_type=2）

    Returns:
        dict: API 响应
    """
    url = f"{API_BASE}/v2/users/{openid}/messages"
    headers = {"Authorization": f"QQBot {token}"}
    body = _build_text_body(content, msg_id, markdown=markdown)
    async with session.post(url, headers=headers, json=body) as resp:
        resp.raise_for_status()
        return await resp.json()


async def send_group_message(
    session: aiohttp.ClientSession,
    token: str,
    group_openid: str,
    content: str,
    msg_id: str,
    *,
    markdown: bool = False,
) -> dict[str, Any]:
    """发送群聊消息

    Args:
        session: HTTP 会话
        token: access_token
        group_openid: 群 openid
        content: 消息内容
        msg_id: 引用的消息 ID（用于回复）
        markdown: 是否使用 markdown 信封（msg_type=2）

    Returns:
        dict: API 响应
    """
    url = f"{API_BASE}/v2/groups/{group_openid}/messages"
    headers = {"Authorization": f"QQBot {token}"}
    body = _build_text_body(content, msg_id, markdown=markdown)
    async with session.post(url, headers=headers, json=body) as resp:
        resp.raise_for_status()
        return await resp.json()


def _build_text_body(
    content: str,
    msg_id: str,
    *,
    markdown: bool = False,
) -> dict[str, Any]:
    """构建消息请求体

    markdown=True 时使用 QQ markdown 信封（msg_type=2），
    否则使用纯文本（msg_type=0）。

    Args:
        content: 消息内容
        msg_id: 引用的消息 ID
        markdown: 是否使用 markdown 信封

    Returns:
        dict: 请求体
    """
    if markdown:
        body: dict[str, Any] = {
            "markdown": {"content": content[:MAX_MESSAGE_LENGTH]},
            "msg_type": MSG_TYPE_MARKDOWN,
            "msg_id": msg_id,
        }
    else:
        body = {
            "content": content[:MAX_MESSAGE_LENGTH],
            "msg_type": MSG_TYPE_TEXT,
            "msg_id": msg_id,
        }
    return body


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


# ── 文本分片（代码块感知） ────────────────────────────────────

# 匹配 ``` 围栏行（开头或闭合）
_RE_FENCE = re.compile(r"^```(\w*)", re.MULTILINE)


def split_text(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """超长文本按段落边界分片，代码块感知

    分片时追踪 ``` 围栏状态：若在代码块内切分，当前片闭合围栏，
    下一片重开围栏（保留语言标记），避免渲染错乱。

    多分片消息附带 (1/n) 编号标记。

    Args:
        text: 原始文本
        max_length: 每片最大长度

    Returns:
        list[str]: 分片列表
    """
    if len(text) <= max_length:
        return [text]

    # 预留编号空间：最多 "(99/99)" = 10 字符
    indicator_reserve = 10
    effective_max = max_length - indicator_reserve

    chunks: list[str] = []
    remaining = text
    in_code_block = False  # 追踪是否在 ``` 代码块内
    code_lang = ""  # 当前代码块的语言标记

    while remaining:
        if len(remaining) <= effective_max:
            # 最后一片：如果在代码块内需要闭合
            if in_code_block:
                chunks.append(remaining.rstrip() + "\n```")
            else:
                chunks.append(remaining)
            break

        # 在有效范围内找切分点
        cut = effective_max
        for sep in ["\n\n", "\n", "。", ".", " "]:
            pos = remaining.rfind(sep, 0, effective_max)
            if pos > effective_max // 2:
                cut = pos + len(sep)
                break

        chunk = remaining[:cut]
        remaining_after = remaining[cut:]

        # 统计当前片中 ``` 围栏的出现次数
        fence_count = len(_RE_FENCE.findall(chunk))

        if in_code_block:
            # 已在代码块内
            if fence_count % 2 == 0:
                # 偶数个新围栏：仍在代码块内 → 闭合 + 重开
                chunk = chunk.rstrip() + "\n```"
                remaining = f"```{code_lang}\n" + remaining_after
            else:
                # 奇数个新围栏：代码块已自然关闭
                in_code_block = False
                code_lang = ""
                remaining = remaining_after
        else:
            # 不在代码块内
            if fence_count % 2 == 0:
                # 偶数个新围栏：仍在代码块外
                remaining = remaining_after
            else:
                # 奇数个新围栏：代码块已开启 → 闭合 + 重开
                in_code_block = True
                # 记录最后一个围栏的语言标记
                last_fence = None
                for m in _RE_FENCE.finditer(chunk):
                    last_fence = m
                if last_fence:
                    code_lang = last_fence.group(1)
                chunk = chunk.rstrip() + "\n```"
                remaining = f"```{code_lang}\n" + remaining_after

        chunks.append(chunk)

    # 添加分片编号
    if len(chunks) > 1:
        total = len(chunks)
        chunks = [f"{c}\n\n({i+1}/{total})" for i, c in enumerate(chunks)]

    return chunks


# ── Markdown 剥离 ─────────────────────────────────────────────

# 预编译正则（用于纯文本回退模式）
_RE_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_RE_ITALIC_STAR = re.compile(r"\*(.+?)\*")
_RE_BOLD_UNDER = re.compile(r"__(.+?)__", re.DOTALL)
_RE_ITALIC_UNDER = re.compile(r"_(.+?)_")
_RE_CODE_BLOCK = re.compile(r"```[a-zA-Z0-9_+-]*\n?", re.DOTALL)
_RE_INLINE_CODE = re.compile(r"`(.+?)`")
_RE_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_RE_LINK = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
_RE_MULTI_NEWLINE = re.compile(r"\n{3,}")


def strip_markdown(text: str) -> str:
    """剥离 markdown 格式，用于纯文本回退模式

    Args:
        text: 含 markdown 的文本

    Returns:
        str: 纯文本
    """
    text = _RE_BOLD.sub(r"\1", text)
    text = _RE_ITALIC_STAR.sub(r"\1", text)
    text = _RE_BOLD_UNDER.sub(r"\1", text)
    text = _RE_ITALIC_UNDER.sub(r"\1", text)
    text = _RE_CODE_BLOCK.sub("", text)
    text = _RE_INLINE_CODE.sub(r"\1", text)
    text = _RE_HEADING.sub("", text)
    text = _RE_LINK.sub(r"\1", text)
    text = _RE_MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()
