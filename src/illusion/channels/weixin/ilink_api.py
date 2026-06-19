"""iLink Bot API 客户端
======================

封装腾讯 iLink Bot API 的 HTTP 调用（长轮询/收发/打字/扫码）。

所有 HTTP 调用延迟导入 aiohttp，确保未安装依赖时模块可导入。

API 端点：
    - ilink/bot/get_bot_qrcode: 获取登录二维码
    - ilink/bot/get_qrcode_status: 轮询扫码状态
    - ilink/bot/getupdates: 长轮询拉取新消息
    - ilink/bot/sendmessage: 发送文本消息
    - ilink/bot/sendtyping: 发送打字状态
    - ilink/bot/getconfig: 获取打字 ticket
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ─── 常量 ──────────────────────────────────────────────────────
ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0  # 131072

EP_GET_UPDATES = "ilink/bot/getupdates"
EP_SEND_MESSAGE = "ilink/bot/sendmessage"
EP_SEND_TYPING = "ilink/bot/sendtyping"
EP_GET_CONFIG = "ilink/bot/getconfig"
EP_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"

LONG_POLL_TIMEOUT_MS = 35_000
API_TIMEOUT_MS = 15_000
CONFIG_TIMEOUT_MS = 10_000
QR_TIMEOUT_MS = 35_000

MAX_MESSAGE_LENGTH = 2000

# 消息类型/状态常量
MSG_TYPE_BOT = 2
MSG_STATE_FINISH = 2
ITEM_TEXT = 1
TYPING_START = 1
TYPING_STOP = 2

# 错误码
SESSION_EXPIRED_ERRCODE = -14
RATE_LIMIT_ERRCODE = -2


@dataclass
class WeixinCredentials:
    """扫码登录后获取的微信凭据

    Attributes:
        account_id: iLink Bot 账号 ID（@im.bot 格式）
        token: 鉴权 token（Bearer）
        base_url: API 入口（可能因重定向改变）
        user_id: bot 自身 ilink user id
    """

    account_id: str
    token: str
    base_url: str
    user_id: str


def _random_wechat_uin() -> str:
    """生成随机 X-WECHAT-UIN 值（每次请求不同）

    Returns:
        str: 随机数字字符串
    """
    return str(random.randint(10**17, 10**18 - 1))


def _build_headers(token: str) -> dict[str, str]:
    """构造 iLink API 请求头

    Args:
        token: Bearer token

    Returns:
        dict: 请求头字典
    """
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
        "X-WECHAT-UIN": _random_wechat_uin(),
    }


async def _api_post(
    session: Any,
    *,
    base_url: str,
    endpoint: str,
    payload: dict,
    token: str,
    timeout_ms: int,
) -> dict[str, Any]:
    """通用 iLink API POST 调用

    Args:
        session: aiohttp.ClientSession
        base_url: API 入口
        endpoint: 端点路径
        payload: 请求体
        token: Bearer token
        timeout_ms: 超时（毫秒）

    Returns:
        dict: 响应 JSON

    Raises:
        asyncio.TimeoutError: 请求超时
    """
    import aiohttp  # 延迟导入

    url = f"{base_url}/{endpoint}"
    timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
    async with session.post(url, json=payload, headers=_build_headers(token), timeout=timeout) as resp:
        return await resp.json(content_type=None)  # iLink 返回 octet-stream，跳过 content-type 检查


async def poll_updates(
    session: Any,
    *,
    base_url: str,
    token: str,
    sync_buf: str,
    timeout_ms: int = LONG_POLL_TIMEOUT_MS,
) -> dict[str, Any]:
    """长轮询拉取新消息

    服务端 hold 请求最多 35s，有消息立即返回。
    超时返回空批次。

    Args:
        session: aiohttp.ClientSession
        base_url: API 入口
        token: Bearer token
        sync_buf: 长轮询游标
        timeout_ms: 超时（毫秒）

    Returns:
        dict: {ret, msgs: [...], get_updates_buf: 新游标}
    """
    try:
        return await _api_post(
            session, base_url=base_url, endpoint=EP_GET_UPDATES,
            payload={"get_updates_buf": sync_buf}, token=token, timeout_ms=timeout_ms,
        )
    except asyncio.TimeoutError:
        return {"ret": 0, "msgs": [], "get_updates_buf": sync_buf}


async def send_message(
    session: Any,
    *,
    base_url: str,
    token: str,
    to: str,
    text: str,
    context_token: str | None,
    client_id: str,
) -> dict[str, Any]:
    """发送文本消息

    Args:
        session: aiohttp.ClientSession
        base_url: API 入口
        token: Bearer token
        to: 目标 user_id
        text: 文本内容
        context_token: 该 peer 的 context_token（iLink 硬约束，必须回传）
        client_id: 客户端消息 ID（幂等去重用）

    Returns:
        dict: API 响应（可能含 errcode）
    """
    if not text or not text.strip():
        raise ValueError("微信消息内容不能为空")

    message: dict[str, Any] = {
        "from_user_id": "",
        "to_user_id": to,
        "client_id": client_id,
        "message_type": MSG_TYPE_BOT,
        "message_state": MSG_STATE_FINISH,
        "item_list": [{"type": ITEM_TEXT, "text_item": {"text": text}}],
    }
    if context_token:
        message["context_token"] = context_token

    return await _api_post(
        session, base_url=base_url, endpoint=EP_SEND_MESSAGE,
        payload={"msg": message}, token=token, timeout_ms=API_TIMEOUT_MS,
    )


async def send_typing(
    session: Any,
    *,
    base_url: str,
    token: str,
    to_user_id: str,
    typing_ticket: str,
    status: int,
) -> None:
    """发送打字状态

    Args:
        session: aiohttp.ClientSession
        base_url: API 入口
        token: Bearer token
        to_user_id: 目标 user_id
        typing_ticket: 打字 ticket（getconfig 获取）
        status: 1=开始（TYPING_START），2=停止（TYPING_STOP）
    """
    await _api_post(
        session, base_url=base_url, endpoint=EP_SEND_TYPING,
        payload={
            "ilink_user_id": to_user_id,
            "typing_ticket": typing_ticket,
            "status": status,
        },
        token=token, timeout_ms=CONFIG_TIMEOUT_MS,
    )


async def get_config(
    session: Any,
    *,
    base_url: str,
    token: str,
    context_token: str,
) -> dict[str, Any]:
    """获取配置（含打字 ticket）

    Args:
        session: aiohttp.ClientSession
        base_url: API 入口
        token: Bearer token
        context_token: peer 的 context_token

    Returns:
        dict: 含 typing_ticket 等配置
    """
    return await _api_post(
        session, base_url=base_url, endpoint=EP_GET_CONFIG,
        payload={"context_token": context_token},
        token=token, timeout_ms=CONFIG_TIMEOUT_MS,
    )


async def get_bot_qrcode(session: Any, *, base_url: str) -> dict[str, Any]:
    """获取登录二维码

    Args:
        session: aiohttp.ClientSession
        base_url: API 入口

    Returns:
        dict: 含 qrcode（hex）和 qrcode_img_content
    """
    return await _api_post(
        session, base_url=base_url, endpoint=f"{EP_GET_BOT_QR}?bot_type=3",
        payload={}, token="", timeout_ms=QR_TIMEOUT_MS,
    )


async def get_qrcode_status(session: Any, *, base_url: str, qrcode: str) -> dict[str, Any]:
    """轮询扫码状态

    Args:
        session: aiohttp.ClientSession
        base_url: API 入口
        qrcode: 二维码 hex token

    Returns:
        dict: 含 status（wait/scaned/confirmed/expired 等）
    """
    return await _api_post(
        session, base_url=base_url, endpoint=EP_GET_QR_STATUS,
        payload={"qrcode": qrcode}, token="", timeout_ms=QR_TIMEOUT_MS,
    )


def _split_text(text: str, max_len: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """在段落边界分片（\\n\\n），尽量不在段落中间断

    Args:
        text: 待分片文本
        max_len: 单片最大长度

    Returns:
        list[str]: 分片列表
    """
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        if len(current) + len(para) + 2 > max_len and current:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks or [text]


async def qr_login_with_browser() -> WeixinCredentials | None:
    """完整的扫码登录流程（浏览器投射二维码）

    流程：
    1. 获取二维码
    2. 用 qrcode 库生成 PNG，启动临时 HTTP 服务投射到浏览器
    3. 轮询扫码状态（wait/scaned/confirmed/expired）
    4. 扫码成功后关闭服务，返回凭据

    Returns:
        WeixinCredentials | None: 凭据，扫码超时返回 None
    """
    import aiohttp  # 延迟导入

    from illusion.config.i18n import t

    print(t("weixin_qr_fetching"))
    base_url = ILINK_BASE_URL
    timeout = aiohttp.ClientTimeout(total=QR_TIMEOUT_MS / 1000)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        # 1. 获取二维码
        qr_resp = await get_bot_qrcode(session, base_url=base_url)
        logger.info("获取二维码完整响应: %s", qr_resp)  # 调试日志
        qrcode_hex = qr_resp.get("qrcode", "")
        if not qrcode_hex:
            logger.error("获取二维码失败: %s", qr_resp)
            return None

        # 2. 启动浏览器二维码投射
        server_info = _serve_qr_in_browser(qrcode_hex)
        print(t("weixin_qr_waiting"))

        # 3. 轮询扫码状态
        refresh_count = 0
        max_refreshes = 3
        try:
            while True:
                status_resp = await get_qrcode_status(session, base_url=base_url, qrcode=qrcode_hex)
                logger.info("扫码状态响应: %s", status_resp)  # 调试日志
                ret = status_resp.get("ret", -1)

                # ret: 0 + 有 bot_token = 扫码确认成功
                if ret == 0 and status_resp.get("bot_token"):
                    print(t("weixin_login_success"))
                    return WeixinCredentials(
                        account_id=status_resp.get("ilink_bot_id", ""),
                        token=status_resp.get("bot_token", ""),
                        base_url=status_resp.get("baseurl", base_url),
                        user_id=status_resp.get("ilink_user_id", ""),
                    )
                # ret: 0 但无 bot_token = 已扫码，等待手机确认
                elif ret == 0:
                    print(t("weixin_qr_scanned"))
                # ret: 1 = 等待扫码
                else:
                    pass  # 继续轮询
        finally:
            server_info["server"].shutdown()


def _serve_qr_in_browser(qr_hex: str) -> dict[str, Any]:
    """启动临时 HTTP 服务投射二维码 PNG 到浏览器

    用标准库 http.server（不依赖 aiohttp——扫码阶段依赖可能未装）。

    Args:
        qr_hex: 二维码内容（hex）

    Returns:
        dict: 含 server/port/state，供后续刷新/关闭
    """
    import base64
    import io
    import threading
    import webbrowser
    from http.server import HTTPServer, BaseHTTPRequestHandler

    import qrcode  # 延迟导入

    # 生成二维码 PNG
    img = qrcode.make(qr_hex)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    # 状态容器（供刷新时更新 HTML）
    state = {"img_b64": img_b64}

    def _build_html() -> str:
        return f"""<html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="5">
<title>微信扫码登录 - IllusionCode</title>
<style>
  body {{ font-family: sans-serif; text-align: center; padding: 40px; background: #f5f5f5; }}
  .card {{ background: white; border-radius: 12px; padding: 30px; display: inline-block; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  img {{ display: block; margin: 20px auto; }}
  h2 {{ color: #333; }}
  p {{ color: #888; }}
</style></head><body>
<div class="card">
<h2>微信扫码登录</h2>
<p>请用微信扫描下方二维码</p>
<img src="data:image/png;base64,{state['img_b64']}" width="280" height="280">
<p style="font-size:12px;color:#aaa">页面每5秒自动刷新</p>
</div>
</body></html>"""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_build_html().encode())

        def log_message(self, *args):
            pass  # 静默日志

    http_server = HTTPServer(("127.0.0.1", 0), Handler)  # 0 = 系统分配端口
    port = http_server.server_address[1]
    threading.Thread(target=http_server.serve_forever, daemon=True).start()
    webbrowser.open(f"http://127.0.0.1:{port}")

    from illusion.config.i18n import t
    print(t("weixin_qr_browser_opened", url=f"http://127.0.0.1:{port}"))
    return {"server": http_server, "port": port, "state": state}


def _refresh_qr_server(server_info: dict[str, Any], qr_hex: str) -> None:
    """刷新二维码服务页面（二维码过期时）

    更新 state 中的 img_b64，页面自动刷新时会拿到新二维码。

    Args:
        server_info: _serve_qr_in_browser 返回的 dict
        qr_hex: 新二维码内容
    """
    import base64
    import io

    import qrcode

    img = qrcode.make(qr_hex)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    server_info["state"]["img_b64"] = base64.b64encode(buf.getvalue()).decode()
