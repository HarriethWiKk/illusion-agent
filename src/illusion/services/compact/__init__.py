"""
会话压缩模块 — 微压缩、LLM 摘要和自动压缩
=============================================

本模块实现会话压缩功能，参考 Claude Code 的压缩系统：
- 微压缩（Microcompact）：清除旧工具结果内容以廉价方式减少 Token 数量
- 完整压缩（Full Compact）：调用 LLM 生成早期消息的结构化摘要
- 自动压缩（Auto-compact）：当 Token 数量超过阈值时自动触发压缩
- 响应式压缩（Reactive Compact）：API 返回 prompt-too-long 时触发压缩
- 上下文警告：接近阈值时通知用户

主要修复：
    - 修复压缩后消息结构混乱（连续 user 消息导致 API 报错）
    - 修复日志格式 bug（~d → ~%d）
    - 添加压缩边界标记（Compact Boundary Marker）
    - 添加图片剥离（压缩前移除图片数据）
    - 添加 PTL 重试（prompt-too-long 时截断重试）
    - 添加响应式压缩
    - 添加上下文警告系统
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from illusion.engine.messages import (
    ConversationMessage,
    ContentBlock,
    MediaBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from illusion.services.token_estimation import estimate_tokens

# 配置模块级日志记录器
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量（来自 Claude Code microCompact.ts / autoCompact.ts）
# ---------------------------------------------------------------------------

# 可压缩的工具列表
COMPACTABLE_TOOLS: frozenset[str] = frozenset({
    "read_file",
    "bash",
    "grep",
    "glob",
    "web_search",
    "web_fetch",
    "edit_file",
    "write_file",
})

# 微压缩清除后的占位符消息
TIME_BASED_MC_CLEARED_MESSAGE = "[Old tool result content cleared]"

# 自动压缩阈值
AUTOCOMPACT_BUFFER_TOKENS = 13_000  # 缓冲区 Token 数
WARNING_THRESHOLD_BUFFER_TOKENS = 20_000  # 警告阈值缓冲区
MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000  # 摘要最大输出 Token 数
MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3  # 最大连续失败次数
MANUAL_COMPACT_BUFFER_TOKENS = 3_000  # 手动压缩缓冲区

# 微压缩默认值
DEFAULT_KEEP_RECENT = 5  # 保留最近工具结果数量
DEFAULT_GAP_THRESHOLD_MINUTES = 60  # 时间间隔阈值（分钟）
DEFAULT_PRESERVE_RECENT = 6  # 默认保留最近消息数量

# Token 估算 padding（保守估计）
TOKEN_ESTIMATION_PADDING = 4 / 3

# 默认上下文窗口大小（按模型系列）
_DEFAULT_CONTEXT_WINDOW = 200_000

# PTL 重试最大次数
MAX_PTL_RETRIES = 3

# 压缩边界标记前缀
COMPACT_BOUNDARY_PREFIX = "[COMPACT_BOUNDARY]"


# ---------------------------------------------------------------------------
# Token 估算
# ---------------------------------------------------------------------------

def estimate_message_tokens(messages: list[ConversationMessage]) -> int:
    """估算会话消息的总 Token 数，包含 4/3 padding。"""
    total = 0
    for msg in messages:
        for block in msg.content:
            if isinstance(block, TextBlock):
                total += estimate_tokens(block.text)
            elif isinstance(block, ToolResultBlock):
                if isinstance(block.content, str):
                    total += estimate_tokens(block.content)
                elif isinstance(block.content, list):
                    for inner in block.content:
                        if isinstance(inner, TextBlock):
                            total += estimate_tokens(inner.text)
                        elif isinstance(inner, MediaBlock):
                            total += 2000  # 图片统一估算为 2000 tokens
            elif isinstance(block, ToolUseBlock):
                total += estimate_tokens(block.name)
                total += estimate_tokens(str(block.input))
            elif isinstance(block, ThinkingBlock):
                total += estimate_tokens(block.thinking)
                if block.signature:
                    total += estimate_tokens(block.signature)
            elif isinstance(block, MediaBlock):
                total += 2000  # 图片统一估算为 2000 tokens
    return int(total * TOKEN_ESTIMATION_PADDING)


def estimate_conversation_tokens(messages: list[ConversationMessage]) -> int:
    """保持向后兼容性的别名。"""
    return estimate_message_tokens(messages)


# ---------------------------------------------------------------------------
# 图片剥离 — 压缩前移除图片数据以减少 Token
# ---------------------------------------------------------------------------

def strip_images_from_messages(
    messages: list[ConversationMessage],
) -> list[ConversationMessage]:
    """将消息中的图片和文档替换为文本占位符。

    在发送给摘要 LLM 之前调用，避免浪费 Token 在 base64 图片数据上。

    Args:
        messages: 原始消息列表

    Returns:
        剥离图片后的新消息列表（不修改原始消息）
    """
    result: list[ConversationMessage] = []
    for msg in messages:
        new_blocks: list[ContentBlock] = []
        for block in msg.content:
            if isinstance(block, MediaBlock):
                new_blocks.append(TextBlock(
                    text=f"[image: {block.file_path}, {block.media_type}]"
                ))
            elif isinstance(block, ToolResultBlock):
                if isinstance(block.content, list):
                    stripped: list[ContentBlock] = []
                    for inner in block.content:
                        if isinstance(inner, MediaBlock):
                            stripped.append(TextBlock(
                                text=f"[image: {inner.file_path}, {inner.media_type}]"
                            ))
                        else:
                            stripped.append(inner)
                    new_blocks.append(ToolResultBlock(
                        tool_use_id=block.tool_use_id,
                        content=stripped,
                        is_error=block.is_error,
                    ))
                else:
                    new_blocks.append(block)
            else:
                new_blocks.append(block)
        result.append(ConversationMessage(role=msg.role, content=new_blocks))
    return result


# ---------------------------------------------------------------------------
# 微压缩 — 清除旧工具结果以廉价方式减少 Token
# ---------------------------------------------------------------------------

def _collect_compactable_tool_ids(messages: list[ConversationMessage]) -> list[str]:
    """遍历消息并收集可压缩的工具使用 ID。"""
    ids: list[str] = []
    for msg in messages:
        if msg.role != "assistant":
            continue
        for block in msg.content:
            if isinstance(block, ToolUseBlock) and block.name in COMPACTABLE_TOOLS:
                ids.append(block.id)
    return ids


def microcompact_messages(
    messages: list[ConversationMessage],
    *,
    keep_recent: int = DEFAULT_KEEP_RECENT,
) -> tuple[list[ConversationMessage], int]:
    """清除旧的可压缩工具结果，保留最近的 keep_recent 个。

    这是廉价的第一轮压缩 — 无需调用 LLM。工具结果内容
    将被替换为 TIME_BASED_MC_CLEARED_MESSAGE。

    Returns:
        (messages, tokens_saved) — 消息在原地修改以提高效率。
    """
    keep_recent = max(1, keep_recent)  # 永远不清除所有结果
    all_ids = _collect_compactable_tool_ids(messages)

    if len(all_ids) <= keep_recent:
        return messages, 0

    # 计算需要保留和清除的 ID 集合
    keep_set = set(all_ids[-keep_recent:])
    clear_set = set(all_ids) - keep_set

    tokens_saved = 0
    for msg in messages:
        if msg.role != "user":
            continue
        new_content: list[ContentBlock] = []
        for block in msg.content:
            if (
                isinstance(block, ToolResultBlock)
                and block.tool_use_id in clear_set
            ):
                old_content = block.content
                if isinstance(old_content, str) and old_content == TIME_BASED_MC_CLEARED_MESSAGE:
                    new_content.append(block)
                    continue
                # 计算节省的 Token 数
                if isinstance(old_content, str):
                    tokens_saved += estimate_tokens(old_content)
                elif isinstance(old_content, list):
                    for inner in old_content:
                        if isinstance(inner, TextBlock):
                            tokens_saved += estimate_tokens(inner.text)
                        elif isinstance(inner, MediaBlock):
                            tokens_saved += 2000
                new_content.append(
                    ToolResultBlock(
                        tool_use_id=block.tool_use_id,
                        content=TIME_BASED_MC_CLEARED_MESSAGE,
                        is_error=block.is_error,
                    )
                )
            else:
                new_content.append(block)
        msg.content = new_content

    if tokens_saved > 0:
        log.info("Microcompact cleared %d tool results, saved ~%d tokens", len(clear_set), tokens_saved)

    return messages, tokens_saved


# ---------------------------------------------------------------------------
# 消息分组 — 按 API 轮次分组（assistant + 对应的 user tool_result）
# ---------------------------------------------------------------------------

def _group_messages_by_turn(
    messages: list[ConversationMessage],
) -> list[list[ConversationMessage]]:
    """将消息按 API 轮次分组。

    每组包含一条 assistant 消息和紧随其后的 user 消息（工具结果）。
    开头的 user 消息（无前置 assistant）单独成组。

    Returns:
        消息组的列表
    """
    groups: list[list[ConversationMessage]] = []
    current_group: list[ConversationMessage] = []

    for msg in messages:
        if msg.role == "assistant" and current_group:
            # 新的 assistant 消息开始新的一组
            groups.append(current_group)
            current_group = [msg]
        else:
            current_group.append(msg)

    if current_group:
        groups.append(current_group)

    return groups


# ---------------------------------------------------------------------------
# 安全分割 — 确保 tool_use/tool_result 对不被切断
# ---------------------------------------------------------------------------

def _find_safe_split_index(
    messages: list[ConversationMessage],
    preserve_recent: int,
) -> int:
    """找到安全的分割索引，确保 tool_use/tool_result 对不被切断。

    从 preserve_recent 位置向前搜索，找到一个不切断工具调用对的分割点。
    如果 newer 部分的 user 消息包含 tool_result，则其对应的 assistant
    消息（含 tool_use）也必须包含在 newer 部分。

    Args:
        messages: 完整消息列表
        preserve_recent: 期望保留的最近消息数量

    Returns:
        安全的分割索引（older = messages[:split], newer = messages[split:]）
    """
    n = len(messages)
    if n <= preserve_recent:
        return 0

    split = n - preserve_recent

    # 收集 newer 部分中所有 tool_result 的 tool_use_id
    newer_tool_result_ids: set[str] = set()
    for msg in messages[split:]:
        if msg.role == "user":
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    newer_tool_result_ids.add(block.tool_use_id)

    if not newer_tool_result_ids:
        # newer 中没有 tool_result，直接分割即可
        return split

    # 向前搜索，找到所有对应的 tool_use 所在的 assistant 消息
    # 确保这些 assistant 消息也在 newer 部分
    for i in range(split - 1, -1, -1):
        msg = messages[i]
        if msg.role == "assistant":
            for block in msg.content:
                if isinstance(block, ToolUseBlock) and block.id in newer_tool_result_ids:
                    # 这个 tool_use 在 older 部分，需要将其纳入 newer
                    newer_tool_result_ids.discard(block.id)
                    if not newer_tool_result_ids:
                        # 所有 tool_use 都已找到
                        # split 应该包含这条 assistant 消息
                        return i

    # 如果还有未找到的 tool_use_id（不应该发生），保守返回 0
    return 0


def _remove_orphaned_tool_results(
    messages: list[ConversationMessage],
) -> list[ConversationMessage]:
    """移除没有对应 tool_use 的孤立 tool_result 块。

    压缩后可能存在 tool_result 但其对应的 tool_use 已被摘要移除，
    这会导致 API 报错 "Message has tool role, but there was no previous
    assistant message with a tool call!"。

    Args:
        messages: 消息列表

    Returns:
        清理后的消息列表
    """
    # 收集所有 tool_use 的 ID
    tool_use_ids: set[str] = set()
    for msg in messages:
        if msg.role == "assistant":
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    tool_use_ids.add(block.id)

    # 检查每个 tool_result 是否有对应的 tool_use
    result: list[ConversationMessage] = []
    for msg in messages:
        if msg.role != "user":
            result.append(msg)
            continue

        # 检查 user 消息中的 tool_result
        has_orphan = False
        for block in msg.content:
            if isinstance(block, ToolResultBlock) and block.tool_use_id not in tool_use_ids:
                has_orphan = True
                break

        if not has_orphan:
            result.append(msg)
            continue

        # 过滤掉孤立的 tool_result
        new_blocks: list[ContentBlock] = []
        for block in msg.content:
            if isinstance(block, ToolResultBlock) and block.tool_use_id not in tool_use_ids:
                log.warning(
                    "Removing orphaned tool_result (tool_use_id=%s) — "
                    "corresponding tool_use was compacted away",
                    block.tool_use_id,
                )
                continue
            new_blocks.append(block)

        if new_blocks:
            result.append(ConversationMessage(role=msg.role, content=new_blocks))
        else:
            # 整条消息都是孤立的 tool_result，跳过
            log.warning("Dropping user message that contained only orphaned tool_results")

    return result


# ---------------------------------------------------------------------------
# 完整压缩 — 基于 LLM 的摘要
# ---------------------------------------------------------------------------

# 不使用工具的前导文本
NO_TOOLS_PREAMBLE = """\
CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.

- Do NOT use read_file, bash, grep, glob, edit_file, write_file, or ANY other tool.
- You already have all the context you need in the conversation above.
- Tool calls will be REJECTED and will waste your only turn — you will fail the task.
- Your entire response must be plain text: an <analysis> block followed by a <summary> block.

"""

# 基础压缩提示词
BASE_COMPACT_PROMPT = """\
Your task is to create a detailed summary of the conversation so far. This summary will replace the earlier messages, so it must capture all important information.

First, draft your analysis inside <analysis> tags. Walk through the conversation chronologically and extract:
- Every user request and intent (explicit and implicit)
- The approach taken and technical decisions made
- Specific code, files, and configurations discussed (with paths and line numbers where available)
- All errors encountered and how they were fixed
- Any user feedback or corrections

Then, produce a structured summary inside <summary> tags with these sections:

1. **Primary Request and Intent**: All user requests in full detail, including nuances and constraints.
2. **Key Technical Concepts**: Technologies, frameworks, patterns, and conventions discussed.
3. **Files and Code Sections**: Every file examined or modified, with specific code snippets and line numbers.
4. **Errors and Fixes**: Every error encountered, its cause, and how it was resolved.
5. **Problem Solving**: Problems solved and approaches that worked vs. didn't work.
6. **All User Messages**: Non-tool-result user messages (preserve exact wording for context).
7. **Pending Tasks**: Explicitly requested work that hasn't been completed yet.
8. **Current Work**: Detailed description of the last task being worked on before compaction.
9. **Optional Next Step**: The single most logical next step, directly aligned with the user's recent request.
"""

# 不使用工具的结尾文本
NO_TOOLS_TRAILER = """
REMINDER: Do NOT call any tools. Respond with plain text only — an <analysis> block followed by a <summary> block. Tool calls will be rejected and you will fail the task."""


def get_compact_prompt(custom_instructions: str | None = None) -> str:
    """构建发送给模型的完整压缩提示词。"""
    prompt = NO_TOOLS_PREAMBLE + BASE_COMPACT_PROMPT
    if custom_instructions and custom_instructions.strip():
        prompt += f"\n\nAdditional Instructions:\n{custom_instructions}"
    prompt += NO_TOOLS_TRAILER
    return prompt


def format_compact_summary(raw_summary: str) -> str:
    """移除 <analysis> 草稿并提取 <summary> 内容。"""
    text = re.sub(r"<analysis>[\s\S]*?</analysis>", "", raw_summary)
    m = re.search(r"<summary>([\s\S]*?)</summary>", text)
    if m:
        text = text.replace(m.group(0), f"Summary:\n{m.group(1).strip()}")
    # 清理多余空行
    text = re.sub(r"\n\n+", "\n\n", text)
    return text.strip()


def build_compact_summary_message(
    summary: str,
    *,
    suppress_follow_up: bool = False,
    recent_preserved: bool = False,
) -> str:
    """创建替换压缩历史的消息。"""
    from illusion.config.i18n import t

    formatted = format_compact_summary(summary)
    text = f"{t('compact_summary_prefix')}\n\n{formatted}"
    if recent_preserved:
        text += f"\n\n{t('compact_recent_preserved')}"
    if suppress_follow_up:
        text += t("compact_suppress_followup")
    return text


# ---------------------------------------------------------------------------
# 压缩边界标记
# ---------------------------------------------------------------------------

def create_compact_boundary_marker() -> ConversationMessage:
    """创建压缩边界标记消息。

    边界标记是一条特殊的 assistant 消息，用于标识压缩发生的位置。
    这确保了压缩后的消息列表不会以两条连续的 user 消息开头。

    Returns:
        边界标记的 ConversationMessage
    """
    return ConversationMessage(
        role="assistant",
        content=[TextBlock(text=COMPACT_BOUNDARY_PREFIX)],
    )


def is_compact_boundary_marker(msg: ConversationMessage) -> bool:
    """检查消息是否为压缩边界标记。"""
    return (
        msg.role == "assistant"
        and len(msg.content) == 1
        and isinstance(msg.content[0], TextBlock)
        and msg.content[0].text.strip() == COMPACT_BOUNDARY_PREFIX
    )


def get_messages_after_compact_boundary(
    messages: list[ConversationMessage],
) -> list[ConversationMessage]:
    """获取最后一个压缩边界标记之后的消息。

    如果没有边界标记，返回所有消息。

    Returns:
        边界标记之后的消息列表
    """
    last_boundary = -1
    for i, msg in enumerate(messages):
        if is_compact_boundary_marker(msg):
            last_boundary = i
    if last_boundary >= 0:
        return messages[last_boundary + 1:]
    return messages


# ---------------------------------------------------------------------------
# 消息结构修复 — 确保压缩后消息角色交替正确
# ---------------------------------------------------------------------------

def _ensure_message_alternation(
    messages: list[ConversationMessage],
) -> list[ConversationMessage]:
    """确保消息列表中 user/assistant 角色正确交替。

    修复以下问题：
    - 连续两条 user 消息之间插入空的 assistant 消息
    - 连续两条 assistant 消息之间插入空的 user 消息
    - 开头不是 user 消息时插入空的 user 消息

    Args:
        messages: 原始消息列表

    Returns:
        修复后的消息列表
    """
    if not messages:
        return messages

    result: list[ConversationMessage] = []

    # 确保第一条消息是 user 角色
    if messages[0].role != "user":
        from illusion.config.i18n import t
        result.append(ConversationMessage.from_user_text(t("compact_conversation_start")))

    for i, msg in enumerate(messages):
        if not result:
            result.append(msg)
            continue

        last_role = result[-1].role
        current_role = msg.role

        if last_role == current_role:
            # 连续相同角色，需要插入间隔消息
            if current_role == "user":
                # 两条连续 user 消息之间插入空 assistant
                result.append(ConversationMessage(
                    role="assistant",
                    content=[TextBlock(text="")],
                ))
            else:
                # 两条连续 assistant 消息之间插入空 user
                result.append(ConversationMessage.from_user_text(""))
        elif last_role == "assistant" and current_role == "user":
            # 正常交替，无需修复
            pass

        result.append(msg)

    return result


# ---------------------------------------------------------------------------
# 自动压缩跟踪
# ---------------------------------------------------------------------------

@dataclass
class AutoCompactState:
    """跨查询循环轮次持久的可变状态。"""

    compacted: bool = False
    turn_counter: int = 0
    consecutive_failures: int = 0
    last_compacted_at_turn: int = 0  # 上次压缩时的轮次
    warning_suppressed: bool = False  # 压缩后暂时抑制警告


# ---------------------------------------------------------------------------
# 上下文警告系统
# ---------------------------------------------------------------------------

@dataclass
class TokenWarningState:
    """上下文使用量的警告状态。"""

    is_above_warning_threshold: bool = False  # 接近阈值
    is_above_autocompact_threshold: bool = False  # 超过自动压缩阈值
    is_at_blocking_limit: bool = False  # 达到阻塞限制
    estimated_tokens: int = 0  # 当前估算的 Token 数
    threshold: int = 0  # 自动压缩阈值
    context_window: int = 0  # 上下文窗口大小


def calculate_token_warning_state(
    messages: list[ConversationMessage],
    model: str,
    *,
    auto_compact_enabled: bool = True,
) -> TokenWarningState:
    """计算当前上下文使用量的警告状态。

    Args:
        messages: 当前消息列表
        model: 模型名称
        auto_compact_enabled: 是否启用了自动压缩

    Returns:
        TokenWarningState 警告状态
    """
    estimated = estimate_message_tokens(messages)
    context_window = get_context_window(model)
    threshold = get_autocompact_threshold(model)

    is_above_autocompact = estimated >= threshold
    is_above_warning = estimated >= (threshold - WARNING_THRESHOLD_BUFFER_TOKENS)
    # 仅当自动压缩关闭时才检查阻塞限制
    is_at_blocking = (
        not auto_compact_enabled
        and estimated >= (context_window - MANUAL_COMPACT_BUFFER_TOKENS)
    )

    return TokenWarningState(
        is_above_warning_threshold=is_above_warning,
        is_above_autocompact_threshold=is_above_autocompact,
        is_at_blocking_limit=is_at_blocking,
        estimated_tokens=estimated,
        threshold=threshold,
        context_window=context_window,
    )


# ---------------------------------------------------------------------------
# 上下文窗口辅助函数
# ---------------------------------------------------------------------------

def get_context_window(model: str) -> int:
    """返回模型的上下文窗口大小。

    优先从 settings.context_window 读取；若未配置或为 0，则返回默认值。
    """
    from illusion.config.settings import load_settings

    settings = load_settings()
    if settings.context_window and settings.context_window > 0:
        return settings.context_window
    return _DEFAULT_CONTEXT_WINDOW


def get_autocompact_threshold(model: str) -> int:
    """计算触发自动压缩的 Token 数量阈值。"""
    context_window = get_context_window(model)
    reserved = min(MAX_OUTPUT_TOKENS_FOR_SUMMARY, 20_000)
    effective = context_window - reserved
    return effective - AUTOCOMPACT_BUFFER_TOKENS


def should_autocompact(
    messages: list[ConversationMessage],
    model: str,
    state: AutoCompactState,
) -> bool:
    """返回是否应该自动压缩会话。"""
    if state.consecutive_failures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES:
        return False
    token_count = estimate_message_tokens(messages)
    threshold = get_autocompact_threshold(model)
    return token_count >= threshold


# ---------------------------------------------------------------------------
# 完整压缩执行（调用 LLM）
# ---------------------------------------------------------------------------

async def compact_conversation(
    messages: list[ConversationMessage],
    *,
    api_client: Any,
    model: str,
    system_prompt: str = "",
    preserve_recent: int = DEFAULT_PRESERVE_RECENT,
    custom_instructions: str | None = None,
    suppress_follow_up: bool = True,
) -> list[ConversationMessage]:
    """通过调用 LLM 生成摘要来压缩消息。

    流程：
    1. 先执行微压缩（廉价 Token 减少）
    2. 剥离图片数据
    3. 分割为待摘要的旧消息和待保留的新消息
    4. 调用 LLM 获取结构化摘要（含 PTL 重试）
    5. 用摘要消息 + 边界标记 + 保留的新消息替换旧消息
    6. 确保消息角色交替正确

    Args:
        messages: 完整的会话历史。
        api_client: 用于摘要调用的 ApiClient 或兼容客户端。
        model: 使用的模型 ID。
        system_prompt: 摘要调用的系统提示词。
        preserve_recent: 保留 verbatim 的最近消息数量。
        custom_instructions: 摘要提示词的可选额外指令。
        suppress_follow_up: 为 True 时指示模型不询问后续问题。

    Returns:
        压缩后的新消息列表。
    """
    from illusion.api.client import ApiMessageRequest, ApiMessageCompleteEvent

    if len(messages) <= preserve_recent:
        return list(messages)

    # 步骤 1：微压缩以廉价方式减少 Token
    messages, tokens_freed = microcompact_messages(messages, keep_recent=DEFAULT_KEEP_RECENT)

    # 步骤 2：剥离图片数据
    messages = strip_images_from_messages(messages)

    pre_compact_tokens = estimate_message_tokens(messages)
    log.info("Compacting conversation: %d messages, ~%d tokens", len(messages), pre_compact_tokens)

    # 步骤 3：安全分割为待摘要和待保留部分（不切断 tool_use/tool_result 对）
    split_index = _find_safe_split_index(messages, preserve_recent)
    older = messages[:split_index]
    newer = messages[split_index:]

    # 步骤 4：构建压缩请求 — 发送旧消息 + 压缩提示词
    compact_prompt = get_compact_prompt(custom_instructions)
    compact_messages_list = list(older) + [ConversationMessage.from_user_text(compact_prompt)]

    summary_text = ""
    ptl_retries = 0

    while ptl_retries <= MAX_PTL_RETRIES:
        try:
            async for event in api_client.stream_message(
                ApiMessageRequest(
                    model=model,
                    messages=compact_messages_list,
                    system_prompt=system_prompt or "You are a conversation summarizer.",
                    max_tokens=MAX_OUTPUT_TOKENS_FOR_SUMMARY,
                    tools=[],  # 压缩调用不使用工具
                )
            ):
                if isinstance(event, ApiMessageCompleteEvent):
                    summary_text = event.message.text
            break  # 成功，退出重试循环
        except Exception as exc:
            error_msg = str(exc).lower()
            is_ptl = "prompt" in error_msg and "long" in error_msg
            if is_ptl and ptl_retries < MAX_PTL_RETRIES:
                ptl_retries += 1
                log.warning(
                    "Compact summary hit prompt-too-long, truncating head (retry %d/%d)",
                    ptl_retries, MAX_PTL_RETRIES,
                )
                # 截断最老的一组消息以减少 Token
                groups = _group_messages_by_turn(compact_messages_list)
                if len(groups) > 2:
                    # 移除最老的一组（保留最后的 compact_prompt）
                    compact_messages_list = []
                    for g in groups[1:]:
                        compact_messages_list.extend(g)
                else:
                    # 无法再截断，放弃
                    log.error("Cannot truncate further for PTL retry")
                    break
            else:
                # 非 PTL 错误或重试次数用尽，重新抛出
                raise

    if not summary_text:
        # 空摘要则返回原始消息
        log.warning("Compact summary was empty — returning original messages")
        return messages

    # 步骤 5：构建新消息列表
    summary_content = build_compact_summary_message(
        summary_text,
        suppress_follow_up=suppress_follow_up,
        recent_preserved=len(newer) > 0,
    )
    summary_msg = ConversationMessage.from_user_text(summary_content)
    boundary_marker = create_compact_boundary_marker()

    result = [summary_msg, boundary_marker, *newer]

    # 步骤 6：清理孤立的 tool_result（没有对应 tool_use 的）
    result = _remove_orphaned_tool_results(result)

    # 步骤 7：确保消息角色交替正确
    result = _ensure_message_alternation(result)

    post_compact_tokens = estimate_message_tokens(result)
    log.info(
        "Compaction done: %d -> %d messages, ~%d -> ~%d tokens (saved ~%d)",
        len(messages), len(result),
        pre_compact_tokens, post_compact_tokens,
        max(0, pre_compact_tokens - post_compact_tokens),
    )
    return result


# ---------------------------------------------------------------------------
# 响应式压缩 — API 返回 prompt-too-long 时触发
# ---------------------------------------------------------------------------

async def reactive_compact(
    messages: list[ConversationMessage],
    *,
    api_client: Any,
    model: str,
    system_prompt: str = "",
    preserve_recent: int = DEFAULT_PRESERVE_RECENT,
) -> tuple[list[ConversationMessage], bool]:
    """当 API 返回 prompt-too-long 错误时，尝试压缩并重试。

    这是最后的防线 — 在自动压缩未能阻止溢出时触发。

    Args:
        messages: 当前消息列表
        api_client: API 客户端
        model: 模型名称
        system_prompt: 系统提示词
        preserve_recent: 保留最近消息数量

    Returns:
        (messages, was_compacted) — 压缩后的消息和是否执行了压缩
    """
    log.info("Reactive compact triggered due to prompt-too-long error")

    # 先尝试微压缩
    messages, tokens_freed = microcompact_messages(messages, keep_recent=DEFAULT_KEEP_RECENT)
    if tokens_freed > 0:
        log.info("Reactive microcompact freed ~%d tokens", tokens_freed)
        return messages, True

    # 微压缩不够，执行完整压缩
    try:
        result = await compact_conversation(
            messages,
            api_client=api_client,
            model=model,
            system_prompt=system_prompt,
            preserve_recent=preserve_recent,
            suppress_follow_up=True,
        )
        return result, True
    except Exception as exc:
        log.error("Reactive compact failed: %s", exc)
        return messages, False


# ---------------------------------------------------------------------------
# 自动压缩集成（从查询循环调用）
# ---------------------------------------------------------------------------

async def auto_compact_if_needed(
    messages: list[ConversationMessage],
    *,
    api_client: Any,
    model: str,
    system_prompt: str = "",
    state: AutoCompactState,
    preserve_recent: int = DEFAULT_PRESERVE_RECENT,
) -> tuple[list[ConversationMessage], bool]:
    """检查是否应该自动压缩，如果是则执行压缩。

    在每个查询循环轮次开始时调用此函数。

    Returns:
        (messages, was_compacted) — 如果已压缩，messages 是新列表。
    """
    if not should_autocompact(messages, model, state):
        return messages, False

    log.info("Auto-compact triggered (failures=%d)", state.consecutive_failures)

    # 先尝试微压缩 — 可能已经足够
    messages, tokens_freed = microcompact_messages(messages)
    if tokens_freed > 0 and not should_autocompact(messages, model, state):
        log.info("Microcompact freed ~%d tokens, auto-compact no longer needed", tokens_freed)
        state.warning_suppressed = True
        return messages, True

    # 需要完整压缩
    try:
        result = await compact_conversation(
            messages,
            api_client=api_client,
            model=model,
            system_prompt=system_prompt,
            preserve_recent=preserve_recent,
            suppress_follow_up=True,
        )
        state.compacted = True
        state.turn_counter += 1
        state.last_compacted_at_turn = state.turn_counter
        state.consecutive_failures = 0
        state.warning_suppressed = True
        return result, True
    except Exception as exc:
        state.consecutive_failures += 1
        log.error(
            "Auto-compact failed (attempt %d/%d): %s",
            state.consecutive_failures,
            MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES,
            exc,
        )
        return messages, False


# ---------------------------------------------------------------------------
# 向后兼容
# ---------------------------------------------------------------------------

def summarize_messages(
    messages: list[ConversationMessage],
    *,
    max_messages: int = 8,
) -> str:
    """生成最近消息的紧凑文本摘要（传统方法，仅用于 /summary 命令）。"""
    selected = messages[-max_messages:]
    lines: list[str] = []
    for message in selected:
        text = message.text.strip()
        if not text:
            continue
        lines.append(f"{message.role}: {text[:300]}")
    return "\n".join(lines)


def compact_messages(
    messages: list[ConversationMessage],
    *,
    preserve_recent: int = DEFAULT_PRESERVE_RECENT,
) -> list[ConversationMessage]:
    """用合成摘要替换旧的会话历史（传统方法，仅作为后备）。

    注意：此方法不调用 LLM，摘要质量较低。
    推荐使用 compact_conversation() 获取高质量摘要。
    """
    if len(messages) <= preserve_recent:
        return list(messages)
    # 安全分割，不切断 tool_use/tool_result 对
    split_index = _find_safe_split_index(messages, preserve_recent)
    older = messages[:split_index]
    newer = messages[split_index:]
    summary = summarize_messages(older)
    if not summary:
        return list(newer)
    result = [
        ConversationMessage(
            role="user",
            content=[TextBlock(text=f"[conversation summary]\n{summary}")],
        ),
        create_compact_boundary_marker(),
        *newer,
    ]
    result = _remove_orphaned_tool_results(result)
    return _ensure_message_alternation(result)


__all__ = [
    "AUTOCOMPACT_BUFFER_TOKENS",
    "AutoCompactState",
    "COMPACTABLE_TOOLS",
    "COMPACT_BOUNDARY_PREFIX",
    "TIME_BASED_MC_CLEARED_MESSAGE",
    "TokenWarningState",
    "auto_compact_if_needed",
    "build_compact_summary_message",
    "calculate_token_warning_state",
    "compact_conversation",
    "compact_messages",
    "create_compact_boundary_marker",
    "estimate_conversation_tokens",
    "estimate_message_tokens",
    "format_compact_summary",
    "get_autocompact_threshold",
    "get_compact_prompt",
    "get_context_window",
    "get_messages_after_compact_boundary",
    "is_compact_boundary_marker",
    "microcompact_messages",
    "reactive_compact",
    "should_autocompact",
    "strip_images_from_messages",
    "summarize_messages",
]
