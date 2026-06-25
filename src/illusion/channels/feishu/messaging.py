"""飞书消息收发
================

封装飞书消息的发送、编辑、文件上传等操作，基于 lark-oapi SDK。

渲染策略（参考 hermes-agent 的 _build_outbound_payload）：
    - 含 markdown 表格 → 纯 text（飞书 post 的 md tag 无法渲染表格）
    - 含 markdown 特征 → post 富文本，内含 {tag:md} 元素让飞书客户端渲染
    - 无 markdown 特征 → 纯 text

所有方法均延迟导入 lark_oapi，确保未安装 SDK 时模块可导入。

函数说明：
    - build_lark_client: 构造飞书 lark 客户端
    - build_outbound_payload: 渲染决策（text/post）
    - send_text: 发送文本消息
    - edit_message: 编辑消息（流式编辑）
    - send_file: 上传并发送文件
    - resolve_receive_id: 解析 chat_id 到 receive_id_type
"""
from __future__ import annotations

import json  # JSON 构造
import logging  # 日志
import re  # markdown 探测
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

# ─── Markdown 探测正则（移植自 hermes feishu.py:153-165）──────────────────
# markdown 特征：标题/列表/有序列表/分隔线/代码块/行内代码/粗体/删除线/下划线/斜体/链接/引用
_MARKDOWN_HINT_RE = re.compile(
    r"(^#{1,6}\s)|(^\s*[-*]\s)|(^\s*\d+\.\s)|(^\s*---+\s*$)|"
    r"(```)|(`[^`\n]+`)|(\*\*[^*\n].+?\*\*)|(~~[^~\n].+?~~)|"
    r"(<u>.+?</u>)|(\*[^*\n]+\*)|(\[[^\]]+\]\([^)]+\))|(^>\s)",
    re.MULTILINE,
)
# 表格探测：一行 |...| 紧跟一行分隔符 |---|
_MARKDOWN_TABLE_RE = re.compile(r"^\|.*\|\n\|[-|: ]+\|", re.MULTILINE)
# 代码块围栏
_MARKDOWN_FENCE_OPEN_RE = re.compile(r"^```([^\n`]*)\s*$")
_MARKDOWN_FENCE_CLOSE_RE = re.compile(r"^```\s*$")
# post 内容格式错误（降级兜底用）
_POST_CONTENT_INVALID_RE = re.compile(
    r"content format of the post type is incorrect", re.IGNORECASE
)
# 降级剥离用的正则
_RE_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_RE_ITALIC_STAR = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_RE_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_RE_HEADING = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_RE_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def build_lark_client(cfg: "FeishuChannelConfig") -> Any:
    """构造飞书 lark 客户端

    Args:
        cfg: 飞书渠道配置

    Returns:
        lark.Client 实例
    """
    import lark_oapi as lark  # type: ignore[import-untyped]  # 延迟导入
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


def build_outbound_payload(text: str) -> tuple[str, str]:
    """渲染决策：根据内容选择 text 或 post 消息类型

    参考自 hermes 的 _build_outbound_payload，三分支决策：
    1. 含 markdown 表格 → 强制 text（飞书 post md tag 无法渲染表格）
    2. 含 markdown 特征 → post 富文本（用 md magic tag 让飞书渲染）
    3. 无 markdown 特征 → 纯 text

    Args:
        text: 待发送文本

    Returns:
        tuple[str, str]: (msg_type, content_json)
    """
    # 1. 表格优先降级为纯文本（飞书 post 渲染表格会空白）
    if _MARKDOWN_TABLE_RE.search(text):
        return "text", json.dumps({"text": text}, ensure_ascii=False)
    # 2. markdown 特征用 post 富文本
    if _MARKDOWN_HINT_RE.search(text):
        return "post", _build_markdown_post_payload(text)
    # 3. 纯文本
    return "text", json.dumps({"text": text}, ensure_ascii=False)


def _build_markdown_post_payload(content: str) -> str:
    """构造飞书 post 富文本 payload

    使用飞书 post 的 md magic tag，让飞书客户端自己渲染 markdown。
    含代码块时按 fence 行切分（否则代码块后的正文会被飞书吞掉）。

    Args:
        content: markdown 文本

    Returns:
        str: post content JSON
    """
    rows = _build_markdown_post_rows(content)
    return json.dumps({"zh_cn": {"content": rows}}, ensure_ascii=False)


def _build_markdown_post_rows(content: str) -> list[list[dict[str, str]]]:
    """把 markdown 切分为飞书 post 的行（每行一个 md 元素）

    飞书 post 的 md 元素有一个 bug：当 md 元素内同时含围栏代码块和后续正文时，
    飞书会把代码块后的内容吞掉。解决：按真实 fence 行切分成多个独立 row。

    Args:
        content: markdown 文本

    Returns:
        list[list[dict]]: post content 结构（行的列表，每行是元素列表）
    """
    if not content:
        return [[{"tag": "md", "text": ""}]]
    # 无代码块：单个 md 元素即可
    if "```" not in content:
        return [[{"tag": "md", "text": content}]]

    rows: list[list[dict[str, str]]] = []
    current: list[str] = []
    in_code_block = False

    def _flush() -> None:
        """把累积的行 flush 成一个独立的 row"""
        if current:
            text = "\n".join(current)
            if text.strip():
                rows.append([{"tag": "md", "text": text}])
            current.clear()

    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if in_code_block:
            # 代码块内：检测关闭 fence
            is_fence = bool(_MARKDOWN_FENCE_CLOSE_RE.match(stripped))
        else:
            # 代码块外：检测开启 fence
            is_fence = bool(_MARKDOWN_FENCE_OPEN_RE.match(stripped))

        if is_fence:
            if not in_code_block:
                _flush()  # 代码块前的 prose 独立成 row
            current.append(raw_line)
            in_code_block = not in_code_block
            if not in_code_block:
                _flush()  # 代码块独立成 row
            continue
        current.append(raw_line)

    _flush()  # 收尾
    return rows or [[{"tag": "md", "text": content}]]


def _strip_markdown_to_plain_text(text: str) -> str:
    """把 markdown 剥离为纯文本（post 降级兜底用）

    Args:
        text: markdown 文本

    Returns:
        str: 剥离后的纯文本
    """
    text = _RE_BOLD.sub(r"\1", text)  # **粗体** → 粗体
    text = _RE_ITALIC_STAR.sub(r"\1", text)  # *斜体* → 斜体
    text = _RE_INLINE_CODE.sub(r"\1", text)  # `代码` → 代码
    text = _RE_HEADING.sub("", text)  # ## 标题 → 标题
    text = _RE_LINK.sub(r"\1", text)  # [文本](url) → 文本
    return text.strip()


async def send_text(client: Any, cfg: "FeishuChannelConfig", chat_id: str,
                    text: str, *, reply_to: str = "") -> str:
    """发送文本消息，返回新消息 ID

    根据内容自动选择 text 或 post 格式（参考 hermes 渲染策略）。
    post 发送失败（内容格式错误）时自动降级为纯文本。

    Args:
        client: lark 客户端
        cfg: 渠道配置
        chat_id: 目标会话
        text: 文本内容
        reply_to: 要回复的消息 ID（可选）

    Returns:
        str: 新消息 ID
    """
    from lark_oapi.api.im.v1 import (  # type: ignore[import-untyped]
        CreateMessageRequest,
    )

    receive_id, receive_id_type = resolve_receive_id(chat_id)

    # 空内容直接拒绝（飞书会返回 230001）
    if not text or not text.strip():
        raise ValueError("飞书消息内容为空")

    # 清理可能引发飞书校验失败的控制字符（保留换行 tab）
    clean_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    msg_type, content = build_outbound_payload(clean_text)
    body = {"receive_id": receive_id, "msg_type": msg_type, "content": content}
    req = (
        CreateMessageRequest.builder()
        .receive_id_type(receive_id_type)
        .request_body(body)
        .build()
    )
    resp = client.im.v1.message.create(req)
    if resp.success():
        return resp.data.message_id  # type: ignore[no-any-return]

    # post 内容格式错误时降级为纯文本
    err_msg = str(getattr(resp, "msg", ""))
    if msg_type == "post" and _POST_CONTENT_INVALID_RE.search(err_msg):
        logger.info("post 内容格式错误，降级为纯文本重发")
        plain = _strip_markdown_to_plain_text(clean_text)
        body = {"receive_id": receive_id, "msg_type": "text",
                "content": json.dumps({"text": plain}, ensure_ascii=False)}
        req = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(body)
            .build()
        )
        resp = client.im.v1.message.create(req)
        if resp.success():
            return resp.data.message_id  # type: ignore[no-any-return]

    raise RuntimeError(f"飞书发送失败: code={resp.code} msg={resp.msg}")


async def edit_message(client: Any, chat_id: str, message_id: str, text: str) -> None:
    """编辑已发送消息（用于流式编辑）

    text 类型消息用 update 接口编辑。
    流式编辑始终用纯 text 格式（避免 post 格式的频繁切换与校验开销），
    最终完整消息（含 markdown）由 finalize 路径重新发送 post。

    失败时记日志（可能限流），不抛异常以免中断流式。

    Args:
        client: lark 客户端
        chat_id: 会话标识（仅用于日志）
        message_id: 要编辑的消息 ID
        text: 新文本
    """
    from lark_oapi.api.im.v1 import (  # noqa: F401
        UpdateMessageRequest,
    )

    # 流式编辑用纯 text 格式（update 接口只支持 text）
    content = json.dumps({"text": text}, ensure_ascii=False)
    req = (
        UpdateMessageRequest.builder()
        .message_id(message_id)
        .request_body({"msg_type": "text", "content": content})
        .build()
    )
    resp = client.im.v1.message.update(req)
    if not resp.success():
        # 230072 = 编辑次数超限（飞书硬限制），属预期，finalize 会新建消息补全
        if resp.code == 230072:
            logger.info("飞书消息编辑次数超限（230072），等待 finalize 补全")
        else:
            logger.warning("飞书编辑消息失败（可能限流）: code=%s msg=%s", resp.code, resp.msg)


def build_card_content(text: str) -> str:
    """构造飞书交互卡片 content JSON（JSON 2.0 结构）

    必须显式声明 schema:"2.0"，飞书才按 2.0 解析——否则默认 1.0，
    而 1.0 的 markdown 标签不支持标题/表格/代码块渲染。
    2.0 的 markdown 组件支持 CommonMark 标准语法（含表格/代码块/列表/标题）。

    Args:
        text: 完整文本（可含 markdown）

    Returns:
        str: 卡片 content JSON 字符串
    """
    card = {
        "schema": "2.0",  # 必须显式声明，否则默认 1.0（不支持表格/标题/代码块）
        "body": {
            "elements": [
                {"tag": "markdown", "content": text},
            ],
        },
    }
    return json.dumps(card, ensure_ascii=False)


async def send_card(client: Any, chat_id: str, text: str, *, reply_to: str = "") -> str:
    """发送交互卡片消息，返回新消息 ID

    卡片用 markdown 元素渲染，支持表格/代码块等富文本。
    卡片可通过 patch_card 无限次更新（无 230072 限制），适合流式输出。

    Args:
        client: lark 客户端
        chat_id: 目标会话
        text: 卡片内容（markdown）
        reply_to: 要回复的消息 ID（可选）

    Returns:
        str: 新消息 ID
    """
    from lark_oapi.api.im.v1 import CreateMessageRequest

    receive_id, receive_id_type = resolve_receive_id(chat_id)
    content = build_card_content(text)
    body = {"receive_id": receive_id, "msg_type": "interactive", "content": content}
    req = (
        CreateMessageRequest.builder()
        .receive_id_type(receive_id_type)
        .request_body(body)
        .build()
    )
    resp = client.im.v1.message.create(req)
    if not resp.success():
        raise RuntimeError(f"飞书卡片发送失败: code={resp.code} msg={resp.msg}")
    return resp.data.message_id  # type: ignore[no-any-return]


async def patch_card(client: Any, message_id: str, text: str) -> None:
    """更新已发送的卡片内容（流式编辑核心）

    卡片的 message.patch 接口无编辑次数限制（不像 text 的 230072），
    适合流式输出过程中反复更新。

    Args:
        client: lark 客户端
        message_id: 要更新的卡片消息 ID
        text: 新的卡片内容（markdown）
    """
    from lark_oapi.api.im.v1 import PatchMessageRequest

    content = build_card_content(text)
    req = (
        PatchMessageRequest.builder()
        .message_id(message_id)
        .request_body({"content": content})
        .build()
    )
    resp = client.im.v1.message.patch(req)
    if not resp.success():
        logger.warning("飞书卡片更新失败: code=%s msg=%s", resp.code, resp.msg)


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
    logger.info("发送文件到飞书 %s: %s", chat_id, path.name)
    # TODO（实现阶段补全）：im.v1.file.create → 拿 file_key → CreateMessageRequest(msg_type=file/image)
