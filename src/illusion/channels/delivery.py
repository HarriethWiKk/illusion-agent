"""渠道投递模块

提供独立的渠道消息投递功能，供 cron scheduler 等进程外场景使用。
构造临时 API 客户端发送消息后关闭，不需要运行中的 Channel 实例。
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from illusion.channels.config import (
        ChannelsConfig,
        FeishuChannelConfig,
        QQChannelConfig,
        WeixinChannelConfig,
    )

logger = logging.getLogger(__name__)


def parse_deliver_to(
    deliver_to: str,
    chat_id: str = "",
) -> tuple[str, str] | None:
    """解析 deliver_to 字段为 (channel_name, target_chat_id)

    解析规则：
        1. 空 → None（本地执行，不投递）
        2. 含 ":" → 拆分为 (channel, chat_id)，显式指定的 chat_id 优先级最高
        3. 仅渠道名 + chat_id 有值 → 用 chat_id（从渠道会话创建的任务回投来源会话）
        4. 仅渠道名 + chat_id 为空 → None（LLM 应在创建任务时填写完整 ID）

    Args:
        deliver_to: 投递目标字符串
        chat_id: 来源会话 ID（从渠道会话创建任务时自动填充）

    Returns:
        tuple[str, str] | None: (channel_name, target_chat_id)，解析失败返回 None
    """
    if not deliver_to:
        return None

    if ":" in deliver_to:
        channel, cid = deliver_to.split(":", 1)
        channel = channel.strip()
        cid = cid.strip()
        if channel and cid:
            return (channel, cid)
        logger.warning("deliver_to 格式无效: %s", deliver_to)
        return None

    # 仅渠道名：用来源会话 chat_id（从渠道会话创建的任务）
    if chat_id:
        return (deliver_to, chat_id)

    logger.info(
        "deliver_to=%s 缺少 chat_id，任务仅在终端执行",
        deliver_to,
    )
    return None


async def deliver_to_channel(
    channel_name: str,
    chat_id: str,
    text: str,
    *,
    config: "ChannelsConfig | None" = None,
) -> bool:
    """投递文本消息到指定渠道会话

    读取 channels.json，构造临时 API 客户端发送后关闭。
    供 cron scheduler 在子进程外调用。

    Args:
        channel_name: 渠道名（"feishu"/"qq"/"weixin"）
        chat_id: 目标会话 ID
        text: 文本内容
        config: 渠道配置（None 时从 channels.json 加载）

    Returns:
        bool: 是否投递成功
    """
    if config is None:
        from illusion.channels.config import load_channels_config
        config = load_channels_config()

    if channel_name == "feishu":
        return await _deliver_feishu(config.feishu, chat_id, text)
    if channel_name == "qq":
        return await _deliver_qq(config.qq, chat_id, text)
    if channel_name == "weixin":
        return await _deliver_weixin(config.weixin, chat_id, text)

    logger.warning("未知渠道: %s", channel_name)
    return False


async def _deliver_feishu(config: "FeishuChannelConfig", chat_id: str, text: str) -> bool:
    """飞书投递：构造 lark.Client → 发送消息

    根据 chat_id 前缀自动判断 receive_id_type：
        - oc_ 开头 → chat_id（群聊）
        - ou_ 开头 → open_id（用户）
        - 其他 → chat_id（默认）
    """
    if not config.enabled:
        logger.warning("飞书渠道未启用，跳过投递")
        return False
    try:
        import json
        from illusion.channels.feishu.messaging import build_lark_client, resolve_receive_id
        try:
            from lark_oapi.api.im.v1 import CreateMessageRequest  # type: ignore[import-untyped]
        except ImportError:
            logger.error("飞书投递需要 lark_oapi")
            return False

        # 复用 feishu adapter 的 ID 解析逻辑，避免两处前缀判断漂移
        _receive_id, receive_id_type = resolve_receive_id(chat_id)

        client = build_lark_client(config)
        body = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        }
        builder = CreateMessageRequest.builder().receive_id_type(receive_id_type)
        builder = builder.request_body(body)  # pyright: ignore[reportArgumentType]
        req = builder.build()
        resp = await asyncio.to_thread(client.im.v1.message.create, req)
        if not resp.success():
            logger.error("飞书投递失败: code=%s msg=%s", resp.code, resp.msg)
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("飞书投递异常: %s", exc)
        return False


async def _deliver_qq(config: "QQChannelConfig", chat_id: str, text: str) -> bool:
    """QQ 投递：构造 aiohttp session → 获取 token → 发送消息

    QQ Bot API v2 为模块级函数，需要传入 session 和 token。
    cron 投递场景无 msg_id（被动消息引用），群聊主动消息可能受限，
    因此采用"先尝试群组失败回退 C2C"的容错策略。
    """
    if not config.enabled:
        logger.warning("QQ 渠道未启用，跳过投递")
        return False
    try:
        import aiohttp
        from illusion.channels.qq.api import (
            ensure_token,
            send_c2c_message,
            send_group_message,
        )

        async with aiohttp.ClientSession() as session:
            token = await ensure_token(
                session, config.app_id, config.client_secret,
            )
            # cron 投递无 msg_id（被动消息引用 ID），传空串。
            # QQ 投递目标类型由 LLM 在 deliver_to 中隐式决定：
            #   群组 → send_group_message；私聊 → send_c2c_message
            # 由于 chat_id 本身不区分 group_openid / user_openid 命名空间，
            # 这里先尝试群组（更常见的 cron 场景），失败时 best-effort 回退到 C2C。
            # 注意：若 chat_id 实为 group_openid，C2C 回退几乎必然失败——
            # 这是有意的折中：保留回退以覆盖 ID 类型可变的边界情况，
            # 失败会被外层 except 捕获并记日志，不会误报成功。
            try:
                await send_group_message(
                    session, token, chat_id, text, msg_id="",
                    markdown=config.markdown_support,
                )
            except Exception as group_exc:  # noqa: BLE001
                logger.warning(
                    "QQ 群组投递失败 (chat_id=%s)，best-effort 尝试 C2C（若 chat_id 为 group_openid 则 C2C 也会失败）: %s",
                    chat_id, group_exc,
                )
                await send_c2c_message(
                    session, token, chat_id, text, msg_id="",
                    markdown=config.markdown_support,
                )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("QQ 投递异常: %s", exc)
        return False


async def _deliver_weixin(config: "WeixinChannelConfig", chat_id: str, text: str) -> bool:
    """微信投递：复用 iLink API 发送文本消息

    cron 投递场景无 context_token（iLink 硬约束：每 peer 回复必须回传），
    尝试从持久化文件加载，加载失败则不传（首次主动消息可能被拒绝）。
    """
    if not config.enabled:
        logger.warning("微信渠道未启用，跳过投递")
        return False
    try:
        import uuid

        from illusion.channels.weixin.ilink_api import (
            EP_SEND_MESSAGE,
            ITEM_TEXT,
            MSG_STATE_FINISH,
            MSG_TYPE_BOT,
            _api_post,
            _make_ssl_connector,
        )

        connector = _make_ssl_connector()
        import aiohttp
        async with aiohttp.ClientSession(trust_env=True, connector=connector) as session:
            # 尝试从持久化文件加载 context_token
            context_token = _load_weixin_context_token(chat_id)

            message = {
                "from_user_id": "",
                "to_user_id": chat_id,
                "client_id": f"cron-{uuid.uuid4().hex[:16]}",
                "message_type": MSG_TYPE_BOT,
                "message_state": MSG_STATE_FINISH,
                "item_list": [{"type": ITEM_TEXT, "text_item": {"text": text}}],
            }
            if context_token:
                message["context_token"] = context_token

            resp = await _api_post(
                session,
                base_url=config.base_url,
                endpoint=EP_SEND_MESSAGE,
                payload={"msg": message},
                token=config.token,
                timeout_ms=15000,
            )
            errcode = resp.get("errcode", 0)
            if errcode != 0:
                logger.error("微信投递失败: errcode=%s resp=%s", errcode, resp)
                return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("微信投递异常: %s", exc)
        return False


def _load_weixin_context_token(user_id: str) -> str:
    """从微信 context_token 持久化文件加载指定用户的 token

    微信 iLink API 硬约束：每 peer 回复必须回传 context_token。
    daemon 运行时会持久化到 channels_data/weixin/context_tokens.json，
    cron 子进程读取该文件获取 context_token。

    Args:
        user_id: 微信用户 ID

    Returns:
        str: context_token，未找到返回空串
    """
    try:
        import json
        from illusion.config.paths import get_channels_data_dir

        token_path = get_channels_data_dir() / "weixin" / "context_tokens.json"
        if not token_path.exists():
            return ""
        data = json.loads(token_path.read_text(encoding="utf-8"))
        return str(data.get(user_id, ""))
    except Exception as exc:  # noqa: BLE001
        logger.warning("加载微信 context_token 失败 (user=%s): %s", user_id, exc)
        return ""
