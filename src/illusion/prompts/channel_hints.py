"""渠道平台感知提示词

集中管理各渠道的平台感知提示词。在渠道对话时注入系统提示词，
让 LLM 知道当前所处的渠道及其能力特性。

注入门控：渠道配置 enabled=false 时不注入（ChannelRunner 不会启动）。
"""
from __future__ import annotations


def get_channel_hint(
    channel_name: str,
    qq_markdown_support: bool | None = None,
) -> str | None:
    """获取指定渠道的平台感知提示词。

    部分能力描述会根据渠道配置动态调整（如 QQ 的 markdown 支持取决于
    markdown_support 配置项，因为 QQ Bot API v2 的 markdown 需要
    预审模板权限，普通开发者账号默认无权限）。

    Args:
        channel_name: 渠道名称（如 "feishu"）
        qq_markdown_support: QQ 渠道的 markdown_support 配置值。
            None 时按保守默认（不支持）处理。

    Returns:
        str | None: 提示词文本，渠道不存在时返回 None
    """
    if channel_name == "feishu":
        return (
            "You are conversing through Feishu (飞书). "
            "Markdown is supported and rendered via interactive cards. "
            "You can use tables, code blocks, lists, headings, and blockquotes. "
            "Files and images can be sent natively via the send_media tool. "
            "Group chats require @mention to respond (configured per channel)."
        )
    if channel_name == "qq":
        # QQ markdown 支持取决于配置（需预审模板权限）
        markdown_supported = bool(qq_markdown_support)
        md_line = (
            "Markdown is supported (msg_type=2). Code blocks with triple backticks are supported. "
            if markdown_supported
            else "Markdown is NOT supported. Use plain text only; avoid backticks, tables, and headings. "
        )
        return (
            "You are conversing through QQ Bot. "
            + md_line
            + "Files and images can be sent natively via the send_media tool. "
            "Group chats require @mention and only support passive replies."
        )
    if channel_name == "weixin":
        return (
            "You are conversing through WeChat (微信). "
            "Markdown is supported but keep messages compact and chat-friendly. "
            "Messages cannot be edited after sending; long replies are split into chunks. "
            "Files and images can be sent natively via the send_media tool. "
            "WeChat bot only supports direct messages (no group chats)."
        )
    return None
