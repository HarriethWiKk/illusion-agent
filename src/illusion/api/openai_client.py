"""
OpenAI 兼容 API 客户端模块
=========================

本模块提供 OpenAI 兼容 API 客户端封装。

主要功能：
    - 流式文本增量生成
    - Anthropic 工具格式到 OpenAI 格式转换
    - 自动重试 transient 错误
    - 支持思维模型（reasoning_content）

类说明：
    - OpenAICompatibleClient: OpenAI 兼容客户端类

使用示例：
    >>> from illusion.api.openai_client import OpenAICompatibleClient
    >>> client = OpenAICompatibleClient(api_key="sk-...")
    >>> request = ApiMessageRequest(model="qwen-plus", messages=[])
    >>> async for event in client.stream_message(request):
    >>>     print(event)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re as _re
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from illusion.api.client import (
    ApiMessageCompleteEvent,
    ApiMessageRequest,
    ApiStreamEvent,
    ApiTextDeltaEvent,
    ApiToolCallStartedEvent,
)
from illusion.api.compat import (
    merge_reasoning_text,
    parse_tool_arguments,
    split_thinking_from_text,
)
from illusion.api.errors import (
    AuthenticationFailure,
    IllusionCodeApiError,
    RateLimitFailure,
    RequestFailure,
)
from illusion.api.usage import UsageSnapshot
from illusion.engine.messages import (
    ContentBlock,
    ConversationMessage,
    MediaBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    _messages_have_media,
    _strip_media_from_messages,
)

# 模块级日志记录器
log = logging.getLogger(__name__)

# 重试配置常量
MAX_RETRIES = 3  # 最大重试次数
BASE_DELAY = 1.0  # 基础延迟（秒）
MAX_DELAY = 30.0  # 最大延迟（秒）


def _serialize_media_for_openai(block: MediaBlock) -> dict[str, Any]:
    """将图片 MediaBlock 转换为 OpenAI 消息内容部分。"""
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{block.media_type};base64,{block.data}"},
    }


def _model_consumes_thought_signature(model: str) -> bool:
    """判断目标模型是否需要回传 Gemini thought_signature（extra_content）。

    Gemini 3 思考模型对每个 functionCall 附加 ``thought_signature``，且要求在后续
    请求中原样回传，否则 API 返回 HTTP 400 "missing thought_signature"。
    但严格的 OpenAI 兼容 provider（如 Fireworks、Mistral）会拒绝任何包含
    ``extra_content`` 字段的请求（"Extra inputs are not permitted"）。
    因此只有当目标模型属于 Gemini 家族时才保留 ``extra_content``，其余一律剥离。

    Args:
        model: 模型名称

    Returns:
        bool: 是否为需要回传 thought_signature 的 Gemini 家族模型
    """
    m = (model or "").lower()
    return "gemini" in m or "gemma" in m


def _extract_extra_content(tc_delta: Any) -> Any:
    """从流式工具调用增量中提取 extra_content（Gemini thought_signature 载体）。

    OpenAI SDK 配置了 ``extra='allow'``，未知字段（如 Gemini 的 ``extra_content``）
    既可通过属性直接访问，也可通过 ``model_extra`` 字典访问。SDK 可能将其解析为
    pydantic 模型，此处统一转为 dict 以便后续处理。

    Args:
        tc_delta: 流式增量中的工具调用对象

    Returns:
        extra_content 的 dict 形式，或 None
    """
    extra = getattr(tc_delta, "extra_content", None)
    if extra is None:
        me = getattr(tc_delta, "model_extra", None) or {}
        if isinstance(me, dict):
            extra = me.get("extra_content")
    if extra is None:
        return None
    if hasattr(extra, "model_dump"):
        try:
            extra = extra.model_dump()
        except Exception:
            pass
    return extra


class _StreamingThoughtTagProcessor:
    """流式文本中实时分离 ``<thought>…</thought>`` 标签内容。

    Gemini 通过 OpenAI 兼容端点返回思考内容时，将其包裹在 ``<thought>`` 标签内
    （而非 ``<think>``），且通过 ``delta.content`` 字段传输而非 ``reasoning_content``。
    如果直接将带标签的文本发给前端，思考内容会与助手回复混在一起显示。

    本处理器维护一个内部缓冲区，逐块接收文本增量并输出 (text, reasoning) 元组。
    它在标签边界处智能缓冲：仅当尾部文本可能是 ``<thought`` 或 ``</thought`` 的
    前缀时才保留，否则立即输出，避免对短文本造成不必要的延迟。

    用法::

        proc = _StreamingThoughtTagProcessor()
        for chunk in delta_chunks:
            for text, reasoning in proc.feed(chunk):
                if reasoning:
                    yield ApiTextDeltaEvent(text="", reasoning=reasoning)
                if text:
                    yield ApiTextDeltaEvent(text=text)
        # 流结束时刷出残留
        for text, reasoning in proc.flush():
            ...同上...
    """

    _OPEN_RE = _re.compile(r'<thought\b[^>]*>', _re.IGNORECASE)
    _CLOSE_RE = _re.compile(r'</thought\b[^>]*>', _re.IGNORECASE)
    # ``<thought`` 前缀候选（不含 ``<``）：用于判断尾部是否可能是截断的标签
    _TAG_PREFIXES = ("t", "th", "tho", "thou", "thoug", "thought",
                     "/t", "/th", "/tho", "/thou", "/thoug", "/thought")
    _TAG_MAX_LEN = 10  # len("</thought") = 10

    def __init__(self) -> None:
        self._buf = ""
        self._in_thought = False

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        """输入文本增量，返回待发送的 (text, reasoning) 元组列表。

        Args:
            chunk: 新的文本增量

        Returns:
            list[tuple[str, str]]: 每项为 (plain_text, reasoning_text)；
                两者之一可为空字符串。
        """
        if not chunk:
            return []
        self._buf += chunk
        return self._process(flush_all=False)

    def flush(self) -> list[tuple[str, str]]:
        """流结束时刷出缓冲区中所有剩余内容。"""
        if not self._buf:
            return []
        return self._process(flush_all=True)

    @classmethod
    def _trailing_tag_prefix_len(cls, text: str) -> int:
        """返回 ``text`` 尾部可能是 ``<thought`` 或 ``</thought`` 前缀的字符数。

        例如 ``"abc<Tho"`` → ``5``（``"<Tho"`` 是 ``"<thought"`` 的前缀）；
        ``"abc"`` → ``0``（尾部不含 ``<``，不可能是标签开头）。

        Args:
            text: 待检查的文本

        Returns:
            int: 可能是标签前缀的尾部字符数，0 表示不需要缓冲
        """
        # 只有当尾部包含 ``<`` 时才可能是标签开头
        lt_pos = text.rfind("<")
        if lt_pos < 0:
            return 0
        tail = text[lt_pos:]
        tail_lower = tail.lower()
        # 检查 tail 是否是 ``<thought...`` 或 ``</thought...`` 的前缀
        for prefix in cls._TAG_PREFIXES:
            tag = "<" + prefix
            if tag.startswith(tail_lower) and len(tail) < len(tag):
                return len(tail)
        # ``tail`` 以 ``<`` 开头但不是任何已知标签前缀 → 不需要缓冲
        return 0

    def _process(self, *, flush_all: bool) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        while self._buf:
            if self._in_thought:
                close_match = self._CLOSE_RE.search(self._buf)
                if close_match:
                    # 输出 </thought> 前的思考内容作为 reasoning
                    thinking = self._buf[:close_match.start()]
                    if thinking:
                        results.append(("", thinking))
                    self._buf = self._buf[close_match.end():]
                    self._in_thought = False
                    continue
                else:
                    # 没有找到关闭标签
                    if flush_all:
                        # 流结束，残留的思考内容全部作为 reasoning 输出
                        if self._buf:
                            results.append(("", self._buf))
                            self._buf = ""
                    else:
                        # 检查尾部是否可能是截断的 </thought 标签
                        hold = self._trailing_tag_prefix_len(self._buf)
                        safe = len(self._buf) - hold
                        if safe > 0:
                            results.append(("", self._buf[:safe]))
                            self._buf = self._buf[safe:]
                        elif hold == 0:
                            # 整个缓冲区都不是标签前缀，全部输出
                            results.append(("", self._buf))
                            self._buf = ""
                    break
            else:
                open_match = self._OPEN_RE.search(self._buf)
                if open_match:
                    # 开标签前的文本作为普通文本输出
                    before = self._buf[:open_match.start()]
                    if before:
                        results.append((before, ""))
                    self._buf = self._buf[open_match.end():]
                    self._in_thought = True
                    continue
                else:
                    # 没有找到开标签
                    if flush_all:
                        if self._buf:
                            results.append((self._buf, ""))
                            self._buf = ""
                    else:
                        # 检查尾部是否可能是截断的 <thought 标签
                        hold = self._trailing_tag_prefix_len(self._buf)
                        safe = len(self._buf) - hold
                        if safe > 0:
                            results.append((self._buf[:safe], ""))
                            self._buf = self._buf[safe:]
                        elif hold == 0:
                            # 整个缓冲区都不是标签前缀，全部输出
                            results.append((self._buf, ""))
                            self._buf = ""
                    break
        return results


def _convert_tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 Anthropic 工具模式转换为 OpenAI function-calling 格式
    
    Anthropic 格式：
        {"name": "...", "description": "...", "input_schema": {...}}
    OpenAI 格式：
        {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
    
    Args:
        tools: Anthropic 格式的工具定义列表
    
    Returns:
        list[dict[str, Any]]: OpenAI 格式的工具定义列表
    """
    result = []
    for tool in tools:
        result.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        })
    return result


def _convert_messages_to_openai(
    messages: list[ConversationMessage],
    system_prompt: str | None,
    *,
    model: str = "",
) -> list[dict[str, Any]]:
    """将 Anthropic 风格消息转换为 OpenAI 聊天格式

    主要差异：
    - Anthropic：系统提示词是单独参数
    - OpenAI：系统提示词是 role="system" 的消息
    - Anthropic：tool_use / tool_result 是 content blocks
    - OpenAI：tool_calls 在 assistant 消息上，tool results 是独立消息

    DeepSeek 等 strict provider 要求每个 tool_use 在紧接的下一条消息中有
    对应的 tool_result。会话中断、中途切换模型、会话恢复等场景可能导致
    tool_result 缺失，本函数自动补齐合成错误结果（content 为
    "Tool execution interrupted"），避免 API 400 错误。

    Args:
        messages: Anthropic 风格的消息列表
        system_prompt: 系统提示词
        model: 目标模型名称，用于决定是否回传 Gemini thought_signature
            （``extra_content``）。仅 Gemini 家族模型保留，其余剥离。

    Returns:
        list[dict[str, Any]]: OpenAI 格式的消息列表
    """
    openai_messages: list[dict[str, Any]] = []

    # 添加系统消息
    if system_prompt:
        openai_messages.append({"role": "system", "content": system_prompt})

    # 跟踪上一条 assistant 消息中尚未收到 tool_result 的 tool_use ID。
    # DeepSeek 等 strict OpenAI 兼容 provider 要求每个 tool_use 在紧接的
    # 下一条消息中有对应的 tool_result。会话中断、中途切换模型、会话恢复
    # 等场景可能导致 tool_result 缺失，此处自动补齐合成错误结果，
    # 避免 API 返回 400 "tool_use ids were found without tool_result"。
    pending_tool_use_ids: list[str] = []

    def _flush_pending() -> None:
        """为所有未收到结果的 tool_use 合成错误 tool 消息。

        文案使用 "Tool execution interrupted"（不含工具名），与运行时层
        （query.py）的 "Tool {name} interrupted" 区分，便于调试时定位
        合成来源。转换层无工具名信息，只有 tool_use_id。
        """
        for tid in pending_tool_use_ids:
            openai_messages.append({
                "role": "tool",
                "tool_call_id": tid,
                "content": "Tool execution interrupted",
            })
        pending_tool_use_ids.clear()

    for msg in messages:
        if msg.role == "assistant":
            # 新的 assistant 消息前，补齐上一轮未完成的 tool_use
            _flush_pending()
            openai_msg = _convert_assistant_message(msg, model=model)
            openai_messages.append(openai_msg)
            # 记录本轮 tool_use ID，等待下一条消息中的 tool_result
            pending_tool_use_ids = [
                b.id for b in msg.content if isinstance(b, ToolUseBlock)
            ]
        elif msg.role == "user":
            # 用户消息可能包含文本、tool_result 或 media blocks
            tool_results = [b for b in msg.content if isinstance(b, ToolResultBlock)]
            text_blocks = [b for b in msg.content if isinstance(b, TextBlock)]
            media_blocks = [b for b in msg.content if isinstance(b, MediaBlock)]

            if tool_results:
                # 检查是否有缺失的 tool_result，合成错误结果补齐
                provided_ids = {tr.tool_use_id for tr in tool_results}
                for tid in pending_tool_use_ids:
                    if tid not in provided_ids:
                        openai_messages.append({
                            "role": "tool",
                            "tool_call_id": tid,
                            "content": "Tool execution interrupted",
                        })
                pending_tool_use_ids.clear()

                # 每个 tool result 成为独立的 role="tool" 消息
                # 注意：OpenAI tool 消息只接受字符串 content，不支持图片
                # 如果 tool result 包含媒体，额外生成一条 user 消息携带媒体
                for tr in tool_results:
                    if isinstance(tr.content, list):
                        # 提取文本和媒体部分
                        tr_media = [b for b in tr.content if isinstance(b, MediaBlock)]
                        openai_messages.append({
                            "role": "tool",
                            "tool_call_id": tr.tool_use_id,
                            "content": tr.text_content,
                        })
                        # 媒体内容通过独立的 user 消息传递
                        if tr_media:
                            media_parts: list[dict[str, Any]] = []
                            for mb in tr_media:
                                media_parts.append(_serialize_media_for_openai(mb))
                            openai_messages.append({
                                "role": "user",
                                "content": media_parts,
                            })
                    else:
                        openai_messages.append({
                            "role": "tool",
                            "tool_call_id": tr.tool_use_id,
                            "content": tr.content,
                        })
            else:
                # 用户消息不含 tool_result
                # 如果有 pending tool_use，先补齐合成结果
                _flush_pending()

            if text_blocks or media_blocks:
                text = "".join(b.text for b in text_blocks)
                if media_blocks:
                    parts: list[dict[str, Any]] = []
                    if text.strip():
                        parts.append({"type": "text", "text": text})
                    for mb in media_blocks:
                        parts.append(_serialize_media_for_openai(mb))
                    openai_messages.append({"role": "user", "content": parts})
                elif text.strip():
                    openai_messages.append({"role": "user", "content": text})
            if not tool_results and not text_blocks and not media_blocks:
                # 空用户消息（不应发生，但需优雅处理）
                openai_messages.append({"role": "user", "content": ""})

    # 处理尾部 orphaned tool_use（assistant 消息后无后续消息）
    _flush_pending()

    return openai_messages


def _convert_assistant_message(msg: ConversationMessage, *, model: str = "") -> dict[str, Any]:
    """将 assistant ConversationMessage 转换为 OpenAI 格式

    支持思维模型（如 Kimi k2.5）的 providers 要求每个包含 tool calls 的 assistant
    消息都有 ``reasoning_content`` 字段。这里统一从 ThinkingBlock 回放 reasoning。

    Gemini 3 思考模型还会对每个 functionCall 附加 ``thought_signature``（通过
    ``extra_content`` 字段）。该签名必须原样回传，否则 API 返回 400。仅当目标
    ``model`` 属于 Gemini 家族时保留 ``extra_content``；严格 provider 会拒绝该字段。

    Args:
        msg: ConversationMessage 对象
        model: 目标模型名称，用于 Gemini thought_signature 门控

    Returns:
        dict[str, Any]: OpenAI 格式的消息
    """
    text_parts = [b.text for b in msg.content if isinstance(b, TextBlock)]
    tool_uses = [b for b in msg.content if isinstance(b, ToolUseBlock)]
    thinking_blocks = [b for b in msg.content if isinstance(b, ThinkingBlock)]

    openai_msg: dict[str, Any] = {"role": "assistant"}

    content, tagged_reasoning = split_thinking_from_text("".join(text_parts))
    # 确保 content 不为 None，否则 DeepSeek 等 API 会报错
    # "Invalid assistant message: content or tool_calls must be set"
    openai_msg["content"] = content if content else None
    if openai_msg["content"] is None and not tool_uses:
        openai_msg["content"] = content or ""

    # 为思维模型回放 reasoning_content（统一来源：ThinkingBlock）
    reasoning = merge_reasoning_text(
        *(b.thinking for b in thinking_blocks),
        tagged_reasoning,
    )
    if reasoning:
        openai_msg["reasoning_content"] = reasoning
    elif tool_uses:
        # 思维模型即使为空也需要此字段
        openai_msg["reasoning_content"] = ""

    if tool_uses:
        # Gemini 3 思考模型要求回传 thought_signature（extra_content）；
        # 严格 provider（Fireworks/Mistral 等）会拒绝未知字段，故按模型门控。
        keep_extra = _model_consumes_thought_signature(model)
        tool_calls: list[dict[str, Any]] = []
        for tu in tool_uses:
            tc: dict[str, Any] = {
                "id": tu.id,
                "type": "function",
                "function": {
                    "name": tu.name,
                    "arguments": json.dumps(tu.input),
                },
            }
            if keep_extra:
                extra = tu.provider_data.get("extra_content")
                if extra is not None:
                    tc["extra_content"] = extra
            tool_calls.append(tc)
        openai_msg["tool_calls"] = tool_calls

    return openai_msg


def _parse_assistant_response(response: Any) -> ConversationMessage:
    """将 OpenAI ChatCompletion 响应解析为 ConversationMessage
    
    Args:
        response: OpenAI API 响应对象
    
    Returns:
        ConversationMessage: 解析后的消息对象
    """
    choice = response.choices[0]
    message = choice.message
    content: list[ContentBlock] = []

    if message.content:
        plain_text, tagged_reasoning = split_thinking_from_text(str(message.content))
        if tagged_reasoning:
            content.append(ThinkingBlock(thinking=tagged_reasoning))
        if plain_text:
            content.append(TextBlock(text=plain_text))

    # 思考内容字段 fallback：reasoning_content > reasoning > reasoning_details（MiniMax）
    reasoning_content = getattr(message, "reasoning_content", None)
    if not reasoning_content:
        reasoning_content = getattr(message, "reasoning", None)
    if not reasoning_content:
        details = getattr(message, "reasoning_details", None)
        if details and isinstance(details, list) and len(details) > 0:
            first = details[0]
            reasoning_content = first.get("text", "") if isinstance(first, dict) else None
    if isinstance(reasoning_content, str) and reasoning_content.strip():
        merged = merge_reasoning_text(
            *(b.thinking for b in content if isinstance(b, ThinkingBlock)),
            reasoning_content,
        )
        content = [b for b in content if not isinstance(b, ThinkingBlock)]
        if merged:
            content.insert(0, ThinkingBlock(thinking=merged))

    if message.tool_calls:
        for tc in message.tool_calls:
            args = parse_tool_arguments(getattr(tc.function, "arguments", ""))
            # 保留 Gemini thought_signature（extra_content）
            extra = _extract_extra_content(tc)
            provider_data: dict[str, Any] = {}
            if extra is not None:
                provider_data["extra_content"] = extra
            content.append(ToolUseBlock(
                id=tc.id,
                name=tc.function.name,
                input=args,
                provider_data=provider_data,
            ))

    return ConversationMessage(role="assistant", content=content)


class OpenAICompatibleClient:
    """OpenAI 兼容 API 客户端
    
    用于 DashScope、GitHub Models 等 OpenAI 兼容 API。
    实现与 AnthropicApiClient 相同的 SupportsStreamingMessages 协议，
    因此可以在 agent 循环中作为直接替代品使用。
    
    Attributes:
        _client: AsyncOpenAI 客户端实例
    """

    def __init__(self, api_key: str, *, base_url: str | None = None, extra_headers: dict[str, str] | None = None) -> None:
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        if extra_headers:
            kwargs["default_headers"] = extra_headers
        self._client = AsyncOpenAI(**kwargs)

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        """流式生成文本增量和最终消息，匹配 Anthropic 客户端接口

        当消息中包含图片但模型不支持时，自动降级为文本描述并重试。

        Args:
            request: API 消息请求

        Yields:
            ApiStreamEvent: 流式事件
        """
        last_error: Exception | None = None
        media_stripped = False

        for attempt in range(MAX_RETRIES + 1):
            try:
                async for event in self._stream_once(request):
                    yield event
                return
            except IllusionCodeApiError as exc:
                if (
                    not media_stripped
                    and _messages_have_media(request.messages)
                    and self._is_media_related_error(exc)
                ):
                    log.warning(
                        "Request failed, possibly due to unsupported image content. "
                        "Retrying with text descriptions instead of images.",
                    )
                    request = ApiMessageRequest(
                        model=request.model,
                        messages=_strip_media_from_messages(request.messages),
                        system_prompt=request.system_prompt,
                        tools=request.tools,
                        max_tokens=request.max_tokens,
                        extra_body=request.extra_body,
                    )
                    media_stripped = True
                    continue
                raise
            except Exception as exc:
                last_error = exc
                if (
                    not media_stripped
                    and _messages_have_media(request.messages)
                    and self._is_media_related_error(exc)
                ):
                    log.warning(
                        "Request failed, possibly due to unsupported image content. "
                        "Retrying with text descriptions instead of images.",
                    )
                    request = ApiMessageRequest(
                        model=request.model,
                        messages=_strip_media_from_messages(request.messages),
                        system_prompt=request.system_prompt,
                        tools=request.tools,
                        max_tokens=request.max_tokens,
                        extra_body=request.extra_body,
                    )
                    media_stripped = True
                    continue

                if attempt >= MAX_RETRIES or not self._is_retryable(exc):
                    raise self._translate_error(exc) from exc

                delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
                log.warning(
                    "OpenAI API request failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1, MAX_RETRIES + 1, delay, exc,
                )
                await asyncio.sleep(delay)

        if last_error is not None:
            raise self._translate_error(last_error) from last_error

    async def _stream_once(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        """单次尝试：流式 OpenAI 聊天完成
        
        Args:
            request: API 消息请求
        
        Yields:
            ApiStreamEvent: 流式事件
        """
        openai_messages = _convert_messages_to_openai(
            request.messages, request.system_prompt, model=request.model,
        )
        openai_tools = _convert_tools_to_openai(request.tools) if request.tools else None

        # 检测是否为 Codex 模型（使用 chatgpt.com/backend-api 或模型名包含 codex）
        # 如果是 Codex 模型，直接走 responses API，避免先尝试 chat/completions 再回退
        if self._should_use_responses_api(request.model):
            log.info("Detected Codex model %s, using responses API directly", request.model)
            async for event in self._stream_via_responses_api(request, openai_messages, openai_tools):
                yield event
            return

        params: dict[str, Any] = {
            "model": request.model,
            "messages": openai_messages,
            "max_tokens": request.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if openai_tools:
            params["tools"] = openai_tools
            # 某些 providers（如 Kimi）在 tool-call 后续请求中对空的 reasoning_content 报错
            # 如果存在 tools，则移除整个 stream_options 键，避免触发模型端思维模式
            # 该模式要求每个 assistant 消息都有 reasoning_content
            params.pop("stream_options", None)

        # 自动注入供应商思考配置
        auto_thinking = self._detect_thinking_config(request.model)
        user_extra_body = request.extra_body or {}

        # effort 字段处理（供应商差异适配）
        if request.effort is not None:
            model_lower = request.model.lower()
            effort_val = request.effort.value

            # Gemini：不传 reasoning_effort（与 thinking_config 互斥，已通过 extra_body 注入）
            # Qwen：不支持 reasoning_effort（用 thinking_budget），跳过
            if not model_lower.startswith(("gemini", "qwen")):
                params["reasoning_effort"] = effort_val

        # extra_body 合并（用户显式配置优先覆盖自动检测）
        merged_extra_body = {**(auto_thinking or {}), **user_extra_body}
        if merged_extra_body:
            params["extra_body"] = merged_extra_body

        # 流式文本增量时收集完整响应
        collected_content = ""
        collected_reasoning = ""
        collected_tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        # Gemini 通过 delta.content 返回 <thought> 标签包裹的思考内容，
        # 需要实时分离以避免思考过程与助手回复混在一起显示。
        thought_processor = _StreamingThoughtTagProcessor()
        usage_data: dict[str, int] = {}

        try:
            stream = await self._client.chat.completions.create(**params)
        except Exception as exc:
            # 检查是否为 effort 不支持错误
            if self._is_effort_unsupported_error(exc) and request.effort is not None:
                # 直接向用户反馈错误，不进行降级
                raise RequestFailure(
                    f"当前模型不支持推理强度 '{request.effort.value}'，请尝试使用其他推理强度级别（如 low/medium/high）"
                ) from exc
            raise
        async for chunk in stream:
            if not chunk.choices:
                # 仅使用量块（某些 providers 在最后发送）
                if chunk.usage:
                    usage_data = {
                        "input_tokens": chunk.usage.prompt_tokens or 0,
                        "output_tokens": chunk.usage.completion_tokens or 0,
                    }
                continue

            delta = chunk.choices[0].delta
            chunk_finish = chunk.choices[0].finish_reason

            if chunk_finish:
                finish_reason = chunk_finish

            # 收集思维模型的思考内容（兼容 GLM、Gemini、DeepSeek、MiniMax 等）
            reasoning_piece = getattr(delta, "reasoning_content", None)
            if not reasoning_piece:
                reasoning_piece = getattr(delta, "reasoning", None)
            if not reasoning_piece:
                # MiniMax 通过 reasoning_details 返回思考内容
                details = getattr(delta, "reasoning_details", None)
                if details and isinstance(details, list) and len(details) > 0:
                    first = details[0]
                    reasoning_piece = first.get("text", "") if isinstance(first, dict) else ""
            reasoning_piece = reasoning_piece or ""
            if reasoning_piece:
                collected_reasoning += reasoning_piece
                yield ApiTextDeltaEvent(text="", reasoning=reasoning_piece)

            # 向用户流式传输文本内容
            if delta.content:
                collected_content += delta.content
                # 通过流式处理器实时分离 <thought> 标签包裹的思考内容，
                # 避免 Gemini 的思考过程与助手回复混在一起显示。
                for text_part, reasoning_part in thought_processor.feed(delta.content):
                    if reasoning_part:
                        collected_reasoning += reasoning_part
                        yield ApiTextDeltaEvent(text="", reasoning=reasoning_part)
                    if text_part:
                        yield ApiTextDeltaEvent(text=text_part)

            # 收集工具调用
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in collected_tool_calls:
                        collected_tool_calls[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                            "extra_content": None,
                        }
                    entry = collected_tool_calls[idx]
                    if tc_delta.id:
                        entry["id"] = tc_delta.id
                    # 捕获 Gemini thought_signature（通过 extra_content 字段返回）
                    extra = _extract_extra_content(tc_delta)
                    if extra is not None:
                        entry["extra_content"] = extra
                    if tc_delta.function:
                        if tc_delta.function.name:
                            # 工具调用开始：模型刚开始生成工具调用时立即通知
                            if not entry["name"]:
                                yield ApiToolCallStartedEvent(
                                    tool_name=tc_delta.function.name,
                                    tool_use_id=tc_delta.id or "",
                                )
                            entry["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            entry["arguments"] += tc_delta.function.arguments

            # chunk 中的使用量（如果 provider 发送）
            if chunk.usage:
                usage_data = {
                    "input_tokens": chunk.usage.prompt_tokens or 0,
                    "output_tokens": chunk.usage.completion_tokens or 0,
                }

        # 刷出流式思考标签处理器中可能残留的内容
        for text_part, reasoning_part in thought_processor.flush():
            if reasoning_part:
                collected_reasoning += reasoning_part
                yield ApiTextDeltaEvent(text="", reasoning=reasoning_part)
            if text_part:
                yield ApiTextDeltaEvent(text=text_part)

        # 构建最终 ConversationMessage
        content: list[ContentBlock] = []
        cleaned_text, tagged_reasoning = split_thinking_from_text(collected_content)
        if cleaned_text:
            content.append(TextBlock(text=cleaned_text))

        for _idx in sorted(collected_tool_calls.keys()):
            tc = collected_tool_calls[_idx]
            # 跳过某些 provider 发送的空/幻影工具调用
            if not tc["name"]:
                continue
            args = parse_tool_arguments(tc["arguments"])
            # 保留 Gemini thought_signature（extra_content）以便后续请求回传
            provider_data: dict[str, Any] = {}
            if tc.get("extra_content") is not None:
                provider_data["extra_content"] = tc["extra_content"]
            content.append(ToolUseBlock(
                id=tc["id"],
                name=tc["name"],
                input=args,
                provider_data=provider_data,
            ))

        merged_reasoning = merge_reasoning_text(collected_reasoning, tagged_reasoning)
        if merged_reasoning:
            content.insert(0, ThinkingBlock(thinking=merged_reasoning))

        final_message = ConversationMessage(
            role="assistant",
            content=content,
        )

        yield ApiMessageCompleteEvent(
            message=final_message,
            usage=UsageSnapshot(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
            ),
            stop_reason=finish_reason,
        )

    def _should_use_responses_api(self, model: str) -> bool:
        """判断是否应使用 Responses API 而非 chat/completions

        Codex 认证使用专用 CodexApiClient，此处仅按模型名判断。

        Args:
            model: 模型名称

        Returns:
            bool: 是否使用 Responses API
        """
        return "codex" in model.lower()

    @staticmethod
    def _detect_thinking_config(model: str) -> dict[str, Any] | None:
        """根据模型名自动检测供应商并构建思考配置 extra_body

        部分供应商（如 GLM、Gemini、Qwen）需要通过 extra_body 显式启用
        思考模式才会返回 reasoning_content。此方法自动检测模型名并构建
        对应的 extra_body 配置。

        Args:
            model: 模型名称

        Returns:
            extra_body 字典，或 None（不需要特殊配置）
        """
        model_lower = model.lower()

        # DeepSeek — 默认开启思考，显式传更可靠
        if "deepseek" in model_lower:
            return {"thinking": {"type": "enabled"}}

        # Doubao（豆包）— 默认关闭，需显式启用，结构同 DeepSeek
        if model_lower.startswith("doubao"):
            return {"thinking": {"type": "enabled"}}

        # GLM（智谱）— 动态思考但不返回内容，需显式启用 + 保留式思考
        if model_lower.startswith("glm"):
            return {"thinking": {"type": "enabled", "clear_thinking": False}}

        # Gemini — 需要 include_thoughts 才返回思考内容
        # 注意：Gemini OpenAI 兼容端点要求 google 字段嵌套在 extra_body 内
        if model_lower.startswith("gemini") and not model_lower.startswith("gemma"):
            return {"extra_body": {"google": {"thinking_config": {"include_thoughts": True}}}}

        # Qwen — 混合模式，显式启用
        if model_lower.startswith("qwen"):
            return {"enable_thinking": True}

        # StepFun — 默认关闭，需显式启用，结构同 Qwen
        if model_lower.startswith("step"):
            return {"enable_thinking": True}

        # MiMo / Kimi / Mistral / xAI / MiniMax — 不需要 extra_body
        return None

    @staticmethod
    def _is_media_related_error(exc: Exception) -> bool:
        """检查错误是否可能由图片内容导致（用于优雅降级判断）

        包括：JSON 解析错误、400/404 错误中与 content/image 相关的消息、
        空响应（某些模型遇到 image_url 直接返回空内容）。

        注意：错误可能已被 _translate_error 转为 IllusionCodeApiError，
        此时 status_code 属性丢失，需从消息字符串中判断。
        """
        error_msg = str(exc).lower()
        status = getattr(exc, "status_code", None)

        # 从错误消息字符串中提取状态码（适配已翻译的异常）
        if status is None:
            for code in (404, 400):
                if f"error code: {code}" in error_msg:
                    status = code
                    break

        # JSON 解析错误：模型返回空响应（遇到不支持的 image_url）
        if "expecting value" in error_msg:
            return True

        # 400/404 错误且包含图片/内容相关关键词
        if status in {400, 404}:
            if any(kw in error_msg for kw in ("image", "media", "content", "param", "unsupported")):
                return True

        return False

    @staticmethod
    def _is_effort_unsupported_error(exc: Exception) -> bool:
        """检测是否为 effort 字段不支持导致的错误

        Args:
            exc: 异常对象

        Returns:
            bool: 是否为 effort 不支持错误
        """
        error_msg = str(exc).lower()
        # 检测常见的 effort 不支持错误消息
        effort_keywords = ["effort", "reasoning_effort", "reasoning effort"]
        unsupported_keywords = ["not supported", "unsupported", "invalid", "unknown"]

        # 检查是否包含 effort 相关关键词
        has_effort_keyword = any(keyword in error_msg for keyword in effort_keywords)
        # 检查是否包含不支持相关关键词
        has_unsupported_keyword = any(keyword in error_msg for keyword in unsupported_keywords)

        # 检查特定的错误模式：unknown variant `max`/`xhigh` 等
        has_variant_error = "unknown variant" in error_msg and any(
            level in error_msg for level in ["max", "xhigh", "low", "medium", "high"]
        )

        return (has_effort_keyword and has_unsupported_keyword) or has_variant_error

    def _convert_messages_to_responses(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None,
    ) -> list[dict[str, Any]]:
        """将 OpenAI 聊天格式消息转换为 Responses API 输入格式"""
        items: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                items.append({"role": "system", "content": content})
            elif role == "assistant" and msg.get("tool_calls"):
                # assistant 消息带 tool_calls：拆分为 message + function_call items
                text_parts = []
                if isinstance(content, str) and content:
                    text_parts.append({"type": "output_text", "text": content})
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append({"type": "output_text", "text": part.get("text", "")})
                if text_parts:
                    items.append({"type": "message", "role": "assistant", "content": text_parts})
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    items.append({
                        "type": "function_call",
                        "call_id": tc.get("id", ""),
                        "name": func.get("name", ""),
                        "arguments": func.get("arguments", "{}"),
                    })
            elif role == "tool":
                # tool 结果消息 → function_call_output item
                if isinstance(content, list):
                    text_items: list[str] = [
                        str(p.get("text", "")) for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    ]
                    output = " ".join(text_items) if text_items else json.dumps(content, ensure_ascii=False)
                else:
                    output = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                items.append({
                    "type": "function_call_output",
                    "call_id": msg.get("tool_call_id", ""),
                    "output": output,
                })
            else:
                # user / assistant 纯文本消息
                text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                items.append({
                    "type": "message",
                    "role": role,
                    "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}],
                })
        return items

    @staticmethod
    def _convert_tools_to_responses(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """将 OpenAI function-calling 工具格式转换为 Responses API 格式"""
        if not tools:
            return None
        result = []
        for tool in tools:
            func = tool.get("function", {})
            result.append({
                "type": "function",
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {}),
            })
        return result

    async def _stream_via_responses_api(
        self,
        request: ApiMessageRequest,
        openai_messages: list[dict[str, Any]],
        openai_tools: list[dict[str, Any]] | None,
    ) -> AsyncIterator[ApiStreamEvent]:
        """通过 OpenAI Responses API 流式生成（chat/completions 不可用时的回退方案）"""
        from openai.types.responses import (
            ResponseCompletedEvent,
            ResponseFunctionCallArgumentsDeltaEvent,
            ResponseFunctionCallArgumentsDoneEvent,
            ResponseOutputItemAddedEvent,
            ResponseTextDeltaEvent,
        )

        input_items = self._convert_messages_to_responses(openai_messages, request.system_prompt)
        resp_tools = self._convert_tools_to_responses(openai_tools)

        params: dict[str, Any] = {
            "model": request.model,
            "input": input_items,
        }
        if request.system_prompt:
            params["instructions"] = request.system_prompt
        if request.max_tokens:
            params["max_output_tokens"] = request.max_tokens
        if resp_tools:
            params["tools"] = resp_tools
        # 添加 effort 字段
        if request.effort is not None:
            params["reasoning"] = {"effort": request.effort.value}

        collected_content = ""
        collected_reasoning = ""
        collected_tool_calls: dict[int, dict[str, Any]] = {}
        usage_data: dict[str, int] = {}

        async with self._client.responses.stream(**params) as stream:
            async for event in stream:
                if isinstance(event, ResponseTextDeltaEvent):
                    collected_content += event.delta
                    yield ApiTextDeltaEvent(text=event.delta)
                    continue

                event_type = str(getattr(event, "type", "") or "")
                if event_type in {
                    "response.reasoning_summary_text.delta",
                    "response.reasoning_text.delta",
                    "response.output_text.reasoning.delta",
                }:
                    delta = getattr(event, "delta", "")
                    if isinstance(delta, str) and delta:
                        collected_reasoning += delta
                        yield ApiTextDeltaEvent(text="", reasoning=delta)
                    continue

                if isinstance(event, ResponseOutputItemAddedEvent):
                    item = event.item
                    if getattr(item, "type", None) == "function_call":
                        idx = event.output_index
                        tool_name = getattr(item, "name", "")
                        tool_use_id = getattr(item, "call_id", "") or getattr(item, "id", "")
                        collected_tool_calls[idx] = {
                            "id": tool_use_id,
                            "name": tool_name,
                            "arguments": "",
                        }
                        # 工具调用开始：模型刚开始生成工具调用时立即通知
                        if tool_name:
                            yield ApiToolCallStartedEvent(
                                tool_name=tool_name,
                                tool_use_id=tool_use_id,
                            )

                elif isinstance(event, ResponseFunctionCallArgumentsDeltaEvent):
                    idx = event.output_index
                    if idx in collected_tool_calls:
                        collected_tool_calls[idx]["arguments"] += event.delta

                elif isinstance(event, ResponseFunctionCallArgumentsDoneEvent):
                    idx = event.output_index
                    if idx in collected_tool_calls:
                        collected_tool_calls[idx]["arguments"] = event.arguments

                elif isinstance(event, ResponseCompletedEvent):
                    resp = event.response
                    if hasattr(resp, "usage") and resp.usage:
                        usage_data = {
                            "input_tokens": getattr(resp.usage, "input_tokens", 0) or 0,
                            "output_tokens": getattr(resp.usage, "output_tokens", 0) or 0,
                        }

        # 构建最终消息
        content: list[ContentBlock] = []
        cleaned_text, tagged_reasoning = split_thinking_from_text(collected_content)
        if cleaned_text:
            content.append(TextBlock(text=cleaned_text))

        for _idx in sorted(collected_tool_calls.keys()):
            tc = collected_tool_calls[_idx]
            if not tc["name"]:
                continue
            args = parse_tool_arguments(tc["arguments"])
            content.append(ToolUseBlock(
                id=tc["id"],
                name=tc["name"],
                input=args,
            ))

        merged_reasoning = merge_reasoning_text(collected_reasoning, tagged_reasoning)
        if merged_reasoning:
            content.insert(0, ThinkingBlock(thinking=merged_reasoning))

        final_message = ConversationMessage(role="assistant", content=content)
        yield ApiMessageCompleteEvent(
            message=final_message,
            usage=UsageSnapshot(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
            ),
            stop_reason="stop",
        )

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """检查异常是否可重试
        
        Args:
            exc: 待检查的异常
        
        Returns:
            bool: 是否可重试
        """
        status = getattr(exc, "status_code", None)
        if status and status in {429, 500, 502, 503}:
            return True
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return True
        return False

    @staticmethod
    def _translate_error(exc: Exception) -> IllusionCodeApiError:
        """转换错误为统一异常类型
        
        Args:
            exc: 原始异常
        
        Returns:
            IllusionCodeApiError: 统一异常类型
        """
        status = getattr(exc, "status_code", None)
        msg = str(exc)
        if status == 401 or status == 403:
            return AuthenticationFailure(msg)
        if status == 429:
            return RateLimitFailure(msg)
        return RequestFailure(msg)
