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
from typing import Any, cast

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


def _make_ssl_connector() -> Any:
    """创建带 certifi CA 证书的 TCPConnector（若可用）

    腾讯 iLink 服务器在部分系统 CA 商店中无法验证（如 macOS Homebrew OpenSSL）。
    安装 certifi 时使用其 Mozilla CA 证书包，否则回退到 aiohttp 默认。

    Returns:
        aiohttp.TCPConnector 或 None
    """
    try:
        import ssl

        import certifi
    except ImportError:
        return None
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    import aiohttp as _aiohttp
    return _aiohttp.TCPConnector(ssl=ssl_ctx)


def _base_info() -> dict[str, Any]:
    """iLink base_info 附加字段"""
    return {"channel_version": "2.2.0"}


def _build_headers(token: str, body: str = "") -> dict[str, str]:
    """构造 iLink API 请求头

    Args:
        token: Bearer token
        body: 请求体字符串（用于计算 Content-Length）

    Returns:
        dict[str, Any]: 请求头字典
    """
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": _random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body:
        headers["Content-Length"] = str(len(body.encode("utf-8")))
    return headers


async def _api_post(
    session: Any,
    *,
    base_url: str,
    endpoint: str,
    payload: dict[str, Any],
    token: str,
    timeout_ms: int,
) -> dict[str, Any]:
    """通用 iLink API POST 调用

    所有 POST 请求自动注入 base_info 字段，手动序列化 JSON 并设置 Content-Length，
    与 hermes-agent 的 iLink 客户端保持一致。

    Args:
        session: aiohttp.ClientSession
        base_url: API 入口
        endpoint: 端点路径
        payload: 请求体
        token: Bearer token
        timeout_ms: 超时（毫秒）

    Returns:
        dict[str, Any]: 响应 JSON

    Raises:
        asyncio.TimeoutError: 请求超时
    """
    import aiohttp  # 延迟导入

    url = f"{base_url}/{endpoint}"
    body = json.dumps({**payload, "base_info": _base_info()}, ensure_ascii=False, separators=(",", ":"))
    timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
    async with session.post(url, data=body, headers=_build_headers(token, body), timeout=timeout) as resp:
        raw = await resp.text()
        if not resp.ok:
            raise RuntimeError(f"iLink POST {endpoint} HTTP {resp.status}: {raw[:200]}")
        return cast(dict[str, Any], json.loads(raw))


async def _api_get(
    session: Any,
    *,
    base_url: str,
    endpoint: str,
    timeout_ms: int,
) -> dict[str, Any]:
    """iLink API GET 调用（用于扫码登录的两个端点）

    这两个端点不需要 token，只需 iLink-App-Id 和 iLink-App-ClientVersion 头。
    响应用 response.text() + json.loads() 解析（避免 content-type 问题）。

    Args:
        session: aiohttp.ClientSession
        base_url: API 入口
        endpoint: 端点路径（含 query 参数）
        timeout_ms: 超时（毫秒）

    Returns:
        dict[str, Any]: 响应 JSON
    """
    url = f"{base_url}/{endpoint}"
    headers = {
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }

    async def _do() -> dict[str, Any]:
        async with session.get(url, headers=headers) as response:
            raw = await response.text()
            if not response.ok:
                raise RuntimeError(f"iLink GET {endpoint} HTTP {response.status}: {raw[:200]}")
            return cast(dict[str, Any], json.loads(raw))

    return await asyncio.wait_for(_do(), timeout=timeout_ms / 1000)


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
        dict[str, Any]: {ret, msgs: [...], get_updates_buf: 新游标}
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
        dict[str, Any]: API 响应（可能含 errcode）
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
    ilink_user_id: str = "",
) -> dict[str, Any]:
    """获取配置（含打字 ticket）

    Args:
        session: aiohttp.ClientSession
        base_url: API 入口
        token: Bearer token
        context_token: peer 的 context_token
        ilink_user_id: 目标用户的 ilink_user_id（API 要求）

    Returns:
        dict[str, Any]: 含 typing_ticket 等配置
    """
    payload: dict[str, Any] = {"context_token": context_token}
    if ilink_user_id:
        payload["ilink_user_id"] = ilink_user_id
    return await _api_post(
        session, base_url=base_url, endpoint=EP_GET_CONFIG,
        payload=payload,
        token=token, timeout_ms=CONFIG_TIMEOUT_MS,
    )


async def get_bot_qrcode(session: Any, *, base_url: str) -> dict[str, Any]:
    """获取登录二维码

    Args:
        session: aiohttp.ClientSession
        base_url: API 入口

    Returns:
        dict[str, Any]: 含 qrcode（hex）和 qrcode_img_content
    """
    return await _api_get(
        session, base_url=base_url,
        endpoint=f"{EP_GET_BOT_QR}?bot_type=3",
        timeout_ms=QR_TIMEOUT_MS,
    )


async def get_qrcode_status(session: Any, *, base_url: str, qrcode: str) -> dict[str, Any]:
    """轮询扫码状态

    Args:
        session: aiohttp.ClientSession
        base_url: API 入口
        qrcode: 二维码 hex token

    Returns:
        dict[str, Any]: 含 status（wait/scaned/confirmed/expired 等）
    """
    return await _api_get(
        session, base_url=base_url,
        endpoint=f"{EP_GET_QR_STATUS}?qrcode={qrcode}",
        timeout_ms=QR_TIMEOUT_MS,
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
    3. 轮询扫码状态（wait/scaned/scaned_but_redirect/expired/confirmed）
    4. 扫码成功后关闭服务，返回凭据

    Returns:
        WeixinCredentials | None: 凭据，扫码超时返回 None
    """
    import time as _time

    import aiohttp  # 延迟导入

    from illusion.config.i18n import t

    print(t("weixin_qr_fetching"))
    base_url = ILINK_BASE_URL
    timeout = aiohttp.ClientTimeout(total=QR_TIMEOUT_MS / 1000)
    connector = _make_ssl_connector()

    async with aiohttp.ClientSession(
        timeout=timeout, trust_env=True, connector=connector,
    ) as session:
        # 1. 获取二维码
        qr_resp = await get_bot_qrcode(session, base_url=base_url)
        logger.info("获取二维码完整响应: %s", qr_resp)  # 调试日志
        qrcode_hex = qr_resp.get("qrcode", "")  # hex token，用于轮询状态
        qr_url = qr_resp.get("qrcode_img_content", "")  # URL，用于生成二维码图片供手机扫描
        if not qrcode_hex:
            logger.error("获取二维码失败: %s", qr_resp)
            return None

        # 2. 启动浏览器二维码投射（用 URL 生成图片，微信才能识别为登录链接）
        qr_content = qr_url or qrcode_hex  # 优先用 URL
        server_info = _serve_qr_in_browser(qr_content)
        print(t("weixin_qr_waiting"))

        # 3. 轮询扫码状态（参照 hermes-agent，使用 status 字段判断）
        deadline = _time.monotonic() + 480  # 总超时 8 分钟
        refresh_count = 0
        max_refreshes = 3
        try:
            while _time.monotonic() < deadline:
                try:
                    status_resp = await get_qrcode_status(
                        session, base_url=base_url, qrcode=qrcode_hex,
                    )
                except asyncio.TimeoutError:
                    await asyncio.sleep(1)
                    continue
                logger.info("扫码状态响应: %s", status_resp)  # 调试日志

                status = str(status_resp.get("status") or "wait")

                if status == "wait":
                    pass  # 等待扫码，继续轮询

                elif status == "scaned":
                    print(t("weixin_qr_scanned"))

                elif status == "scaned_but_redirect":
                    redirect_host = str(status_resp.get("redirect_host") or "")
                    if redirect_host:
                        base_url = f"https://{redirect_host}"
                        logger.info("扫码重定向到: %s", base_url)
                        print(t("weixin_qr_redirect"))

                elif status == "expired":
                    refresh_count += 1
                    if refresh_count > max_refreshes:
                        print(t("weixin_qr_timeout"))
                        return None
                    print(t("weixin_qr_expired"))
                    try:
                        qr_resp = await get_bot_qrcode(session, base_url=ILINK_BASE_URL)
                        qrcode_hex = qr_resp.get("qrcode", "")
                        qr_url = qr_resp.get("qrcode_img_content", "")
                        if not qrcode_hex:
                            logger.error("刷新二维码失败: %s", qr_resp)
                            return None
                        # 更新浏览器中的二维码图片
                        _refresh_qr_server(server_info, qr_url or qrcode_hex)
                    except Exception as exc:
                        logger.error("刷新二维码异常: %s", exc)
                        return None

                elif status == "confirmed":
                    account_id = str(status_resp.get("ilink_bot_id") or "")
                    token = str(status_resp.get("bot_token") or "")
                    base_url = str(status_resp.get("baseurl") or base_url)
                    user_id = str(status_resp.get("ilink_user_id") or "")
                    if not account_id or not token:
                        logger.error("扫码确认但凭据不完整: %s", status_resp)
                        return None
                    print(t("weixin_login_success"))
                    return WeixinCredentials(
                        account_id=account_id,
                        token=token,
                        base_url=base_url,
                        user_id=user_id,
                    )

                await asyncio.sleep(1)

            # 超时
            print(t("weixin_qr_timeout"))
            return None
        finally:
            server_info["server"].shutdown()


def _serve_qr_in_browser(qr_hex: str) -> dict[str, Any]:
    """启动临时 HTTP 服务投射二维码 PNG 到浏览器

    用标准库 http.server（不依赖 aiohttp——扫码阶段依赖可能未装）。

    Args:
        qr_hex: 二维码内容（hex）

    Returns:
        dict[str, Any]: 含 server/port/state，供后续刷新/关闭
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
    img.save(buf, format="PNG")  # type: ignore[call-arg]
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
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_build_html().encode())

        def log_message(self, *args: Any) -> None:
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
        server_info: _serve_qr_in_browser 返回的 dict[str, Any]
        qr_hex: 新二维码内容
    """
    import base64
    import io

    import qrcode

    img = qrcode.make(qr_hex)
    buf = io.BytesIO()
    img.save(buf, format="PNG")  # type: ignore[call-arg]
    server_info["state"]["img_b64"] = base64.b64encode(buf.getvalue()).decode()
