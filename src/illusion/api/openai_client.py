"""
OpenAI 兼容 API 客户端模块
=========================

本模块提供 OpenAI 兼容 API 客户端封装，支持阿里巴巴 DashScope、GitHub Models 等提供商。

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
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from illusion.api.client import (
    ApiMessageCompleteEvent,
    ApiMessageRequest,
    ApiStreamEvent,
    ApiTextDeltaEvent,
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
    ConversationMessage,
    ContentBlock,
    MediaBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)

# 模块级日志记录器
log = logging.getLogger(__name__)

# 重试配置常量
MAX_RETRIES = 3  # 最大重试次数
BASE_DELAY = 1.0  # 基础延迟（秒）
MAX_DELAY = 30.0  # 最大延迟（秒）


def _serialize_media_for_openai(block: MediaBlock) -> dict[str, Any]:
    """将 MediaBlock 转换为 OpenAI 消息内容部分。"""
    if block.category == "image":
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{block.media_type};base64,{block.data}"},
        }
    if block.category == "audio":
        fmt = block.media_type.split("/")[-1]
        if fmt == "mpeg":
            fmt = "mp3"
        return {"type": "input_audio", "input_audio": {"data": block.data, "format": fmt}}
    # video — 以 image_url 方式传递
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{block.media_type};base64,{block.data}"},
    }


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
) -> list[dict[str, Any]]:
    """将 Anthropic 风格消息转换为 OpenAI 聊天格式
    
    主要差异：
    - Anthropic：系统提示词是单独参数
    - OpenAI：系统提示词是 role="system" 的消息
    - Anthropic：tool_use / tool_result 是 content blocks
    - OpenAI：tool_calls 在 assistant 消息上，tool results 是独立消息
    
    Args:
        messages: Anthropic 风格的消息列表
        system_prompt: 系统提示词
    
    Returns:
        list[dict[str, Any]]: OpenAI 格式的消息列表
    """
    openai_messages: list[dict[str, Any]] = []

    # 添加系统消息
    if system_prompt:
        openai_messages.append({"role": "system", "content": system_prompt})

    for msg in messages:
        if msg.role == "assistant":
            openai_msg = _convert_assistant_message(msg)
            openai_messages.append(openai_msg)
        elif msg.role == "user":
            # 用户消息可能包含文本、tool_result 或 media blocks
            tool_results = [b for b in msg.content if isinstance(b, ToolResultBlock)]
            text_blocks = [b for b in msg.content if isinstance(b, TextBlock)]
            media_blocks = [b for b in msg.content if isinstance(b, MediaBlock)]

            if tool_results:
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

    return openai_messages


def _convert_assistant_message(msg: ConversationMessage) -> dict[str, Any]:
    """将 assistant ConversationMessage 转换为 OpenAI 格式

    支持思维模型（如 Kimi k2.5）的 providers 要求每个包含 tool calls 的 assistant
    消息都有 ``reasoning_content`` 字段。这里统一从 ThinkingBlock 回放 reasoning。

    Args:
        msg: ConversationMessage 对象

    Returns:
        dict[str, Any]: OpenAI 格式的消息
    """
    text_parts = [b.text for b in msg.content if isinstance(b, TextBlock)]
    tool_uses = [b for b in msg.content if isinstance(b, ToolUseBlock)]
    thinking_blocks = [b for b in msg.content if isinstance(b, ThinkingBlock)]

    openai_msg: dict[str, Any] = {"role": "assistant"}

    content, tagged_reasoning = split_thinking_from_text("".join(text_parts))
    openai_msg["content"] = content if content else None

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
        openai_msg["tool_calls"] = [
            {
                "id": tu.id,
                "type": "function",
                "function": {
                    "name": tu.name,
                    "arguments": json.dumps(tu.input),
                },
            }
            for tu in tool_uses
        ]

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

    reasoning_content = getattr(message, "reasoning_content", None)
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
            content.append(ToolUseBlock(
                id=tc.id,
                name=tc.function.name,
                input=args,
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
        
        Args:
            request: API 消息请求
        
        Yields:
            ApiStreamEvent: 流式事件
        """
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                async for event in self._stream_once(request):
                    yield event
                return
            except IllusionCodeApiError:
                raise
            except Exception as exc:
                last_error = exc
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
        openai_messages = _convert_messages_to_openai(request.messages, request.system_prompt)
        openai_tools = _convert_tools_to_openai(request.tools) if request.tools else None

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

        # 流式文本增量时收集完整响应
        collected_content = ""
        collected_reasoning = ""
        collected_tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        usage_data: dict[str, int] = {}

        try:
            stream = await self._client.chat.completions.create(**params)
        except Exception as exc:
            # 某些模型（如 gpt-5.2-codex）不支持 /chat/completions，自动回退到 /responses
            if self._is_chat_endpoint_error(exc):
                log.info("Model %s does not support chat/completions, falling back to responses API", request.model)
                async for event in self._stream_via_responses_api(request, openai_messages, openai_tools):
                    yield event
                return
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

            # 收集思维模型的 reasoning_content（不向用户显示）
            reasoning_piece = getattr(delta, "reasoning_content", None) or ""
            if reasoning_piece:
                collected_reasoning += reasoning_piece
                yield ApiTextDeltaEvent(text="", reasoning=reasoning_piece)

            # 向用户流式传输文本内容
            if delta.content:
                collected_content += delta.content
                yield ApiTextDeltaEvent(text=delta.content)

            # 收集工具调用
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in collected_tool_calls:
                        collected_tool_calls[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    entry = collected_tool_calls[idx]
                    if tc_delta.id:
                        entry["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            entry["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            entry["arguments"] += tc_delta.function.arguments

            # chunk 中的使用量（如果 provider 发送）
            if chunk.usage:
                usage_data = {
                    "input_tokens": chunk.usage.prompt_tokens or 0,
                    "output_tokens": chunk.usage.completion_tokens or 0,
                }

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
            content.append(ToolUseBlock(
                id=tc["id"],
                name=tc["name"],
                input=args,
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

    @staticmethod
    def _is_chat_endpoint_error(exc: Exception) -> bool:
        """检查是否为 chat/completions 端点不支持的错误（需回退到 responses API）"""
        error_msg = str(getattr(exc, "message", "")) or str(exc)
        return (
            getattr(exc, "status_code", None) == 400
            and "chat/completions" in error_msg
            and "not accessible" in error_msg.lower()
        )

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
                    text_parts = [
                        p.get("text", "") for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    ]
                    output = " ".join(text_parts) if text_parts else json.dumps(content, ensure_ascii=False)
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
                        collected_tool_calls[idx] = {
                            "id": getattr(item, "call_id", "") or getattr(item, "id", ""),
                            "name": getattr(item, "name", ""),
                            "arguments": "",
                        }

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
