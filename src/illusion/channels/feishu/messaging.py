"""飞书消息收发
================

封装飞书消息的发送、编辑、文件上传等操作，基于 lark-oapi SDK。

所有方法均延迟导入 lark_oapi，确保未安装 SDK 时模块可导入。

函数说明：
    - build_lark_client: 构造飞书 lark 客户端
    - send_text: 发送文本/post 消息
    - edit_message: 编辑已发送消息
    - send_file: 上传并发送文件
    - resolve_receive_id: 解析 chat_id 到 receive_id_type
"""
from __future__ import annotations

import logging  # 日志
from pathlib import Path  # 路径
from typing import TYPE_CHECKING, Any  # 类型

if TYPE_CHECKING:
    from illusion.channels.config import FeishuChannelConfig  # 配置

logger = logging.getLogger(__name__)  # 日志器

# 飞书域名映射
_DOMAINS = {
    "feishu": "https://open.feishu.cn",
    "lark": "https://open.larksuite.com",
}


def build_lark_client(cfg: "FeishuChannelConfig") -> Any:
    """构造飞书 lark 客户端

    Args:
        cfg: 飞书渠道配置

    Returns:
        lark.Client 实例
    """
    import lark_oapi as lark  # 延迟导入
    return (
        lark.Client.builder()
        .app_id(cfg.app_id)
        .app_secret(cfg.app_secret)
        .domain(_DOMAINS.get(cfg.domain, _DOMAINS["feishu"]))
        .build()
    )


def resolve_receive_id(chat_id: str) -> tuple[str, str]:
    """解析 chat_id 到 (receive_id, receive_id_type)

    路由规则（与 hermes 一致）：
    - ou_ 前缀 → open_id 类型
    - 其他 → chat_id 类型

    Args:
        chat_id: 原始会话标识

    Returns:
        tuple[str, str]: (receive_id, receive_id_type)
    """
    if chat_id.startswith("ou_"):
        return chat_id, "open_id"
    return chat_id, "chat_id"


async def send_text(client: Any, cfg: "FeishuChannelConfig", chat_id: str,
                    text: str, *, reply_to: str = "") -> str:
    """发送文本消息，返回新消息 ID

    含 markdown 的文本用 post 富文本格式（表格降级为纯文本）。

    Args:
        client: lark 客户端
        cfg: 渠道配置
        chat_id: 目标会话
        text: 文本内容
        reply_to: 要回复的消息 ID

    Returns:
        str: 新消息 ID
    """
    import json  # JSON 构造
    from lark_oapi.api.im.v1 import (  # type: ignore[import-not-found]
        CreateMessageRequest, CreateMessageRequestBody,
    )

    receive_id, receive_id_type = resolve_receive_id(chat_id)

    # 判断是否含 markdown，构造对应消息格式
    if _has_markdown(text):
        msg_type, content = _build_post_content(text)
    else:
        msg_type = "text"
        content = json.dumps({"text": text}, ensure_ascii=False)

    body = CreateMessageRequestBody(
        receive_id=receive_id,
        msg_type=msg_type,
        content=content,
    )
    req = CreateMessageRequest(
        receive_id_type=receive_id_type,
        request_body=body,
    )
    resp = client.im.v1.message.create(req)
    if not resp.success():
        raise RuntimeError(f"飞书发送失败: code={resp.code} msg={resp.msg}")
    return resp.data.message_id  # type: ignore[union-attr]


def _has_markdown(text: str) -> bool:
    """检测文本是否含 markdown 语法

    Args:
        text: 待检测文本

    Returns:
        bool: 含 markdown 标记返回 True
    """
    markers = ("**", "`", "# ", "- ", "* ", "|", "](")
    return any(m in text for m in markers)


def _build_post_content(text: str) -> tuple[str, str]:
    """把 markdown 文本构造为飞书 post 富文本内容

    简化实现：按行拆分，每行作为一个 text_run。
    复杂的表格/图片等降级为纯文本。

    Args:
        text: markdown 文本

    Returns:
        tuple[str, str]: (msg_type, content_json)
    """
    import json
    lines = text.split("\n")
    title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("#") else ""
    content_lines = lines[1:] if title else lines
    post = {
        "zh_cn": {
            "title": title or "",
            "content": [[{"tag": "text", "text": line}] for line in content_lines if line],
        }
    }
    return "post", json.dumps(post, ensure_ascii=False)


async def edit_message(client: Any, chat_id: str, message_id: str, text: str) -> None:
    """编辑已发送消息的文本

    用于流式编辑。失败时记日志（可能限流），不抛异常以免中断流式。

    Args:
        client: lark 客户端
        chat_id: 会话标识（仅用于日志）
        message_id: 要编辑的消息 ID
        text: 新文本
    """
    import json  # JSON 构造
    from lark_oapi.api.im.v1 import (  # type: ignore[import-not-found]
        PatchMessageRequest, PatchMessageRequestBody,
    )

    content = json.dumps({"text": text}, ensure_ascii=False)
    req = PatchMessageRequest(
        message_id=message_id,
        request_body=PatchMessageRequestBody(content=content),
    )
    resp = client.im.v1.message.patch(req)
    if not resp.success():
        logger.warning("飞书编辑消息失败（可能限流）: code=%s msg=%s", resp.code, resp.msg)


async def send_file(client: Any, cfg: "FeishuChannelConfig", chat_id: str, file_path: str) -> None:
    """上传并发送文件

    Args:
        client: lark 客户端
        cfg: 渠道配置
        chat_id: 目标会话
        file_path: 本地文件路径
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 先上传文件拿 file_key，再发消息（实现细节在 lark-oapi SDK）
    # 此处为框架，实际 file create 调用见 SDK 文档
    logger.info("发送文件到飞书 %s: %s", chat_id, path.name)
    # TODO（实现阶段补全）：im.v1.file.create → 拿 file_key → CreateMessageRequest(msg_type=file/image)
