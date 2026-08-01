"""
检查点存储服务
==============

基于单文件 JSONL append-only 模式的会话持久化存储。

核心设计：
    - 3 种 role 行：_checkpoint / _usage / 普通消息
    - rewind 原地重写，restore 单遍扫描重建内存状态
    - 异步文件 I/O（aiofiles），避免阻塞事件循环

主要组件：
    - RestoreResult: restore 结果数据类
    - CheckpointStore: context.jsonl 读写管理器

使用示例：
    >>> store = CheckpointStore(Path("./.illusion/session"))
    >>> await store.append_message(message)
    >>> result = await store.restore()
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiofiles
from pydantic import ValidationError

from illusion.api.usage import UsageSnapshot
from illusion.engine.messages import ConversationMessage


@dataclass
class RestoreResult:
    """CheckpointStore.restore() 的结果。

    Attributes:
        messages: 重建的对话消息列表
        usage_input: 最后一个 _usage 的 input_tokens（累积）
        usage_output: 最后一个 _usage 的 output_tokens（累积）
        usage_cache_read: 最后一个 _usage 的 cache_read_input_tokens（累积）
        usage_cache_creation: 最后一个 _usage 的 cache_creation_input_tokens（累积）
        last_usage: 最后一次 API 调用的单次用量（含缓存分项），无则 None
        last_usage_message_count: 最后一次 API 调用时的消息数快照
        checkpoint_count: _checkpoint 行数（用于 rewind 计数）
    """
    messages: list[ConversationMessage]
    usage_input: int
    usage_output: int
    usage_cache_read: int
    usage_cache_creation: int
    last_usage: UsageSnapshot | None
    last_usage_message_count: int
    checkpoint_count: int


class CheckpointStore:
    """context.jsonl 的 append-only 持久化存储。

    单文件 JSONL，含 3 种 role：_checkpoint /
    _usage / 普通消息。append-only 保证崩溃安全，
    rewind 通过原地重写实现。

    Attributes:
        next_checkpoint_id: 下一个 _checkpoint 的 id（单调递增）
    """

    def __init__(self, session_dir: Path, session_id: str) -> None:
        """初始化 CheckpointStore。

        采用延迟创建策略：构造时不创建目录，第一次 _append_line 时才 mkdir。
        这样空会话（启动后未发消息）不会在磁盘留下空目录。

        Args:
            session_dir: 会话目录（含 context.jsonl）
            session_id: 会话 ID

        Raises:
            InvalidSessionIdError: 当 session_id 含路径遍历字符时
        """
        # 防御路径遍历：session_id 应为纯目录名
        from illusion.services.session_storage import _validate_session_id
        _validate_session_id(session_id)
        self._session_dir = session_dir
        self._session_id = session_id
        self._file = session_dir / "context.jsonl"
        self._io_lock = asyncio.Lock()
        self._next_checkpoint_id = 0
        self._dir_ensured = False  # 延迟创建标志

    @property
    def next_checkpoint_id(self) -> int:
        """返回下一个 checkpoint id。"""
        return self._next_checkpoint_id

    @property
    def session_id(self) -> str:
        """返回会话 ID。"""
        return self._session_id

    async def append_checkpoint(self) -> int:
        """追加 _checkpoint 行，返回 checkpoint id。

        Returns:
            int: 新分配的 checkpoint id
        """
        checkpoint_id = self._next_checkpoint_id
        self._next_checkpoint_id += 1
        record = {"role": "_checkpoint", "id": checkpoint_id}
        await self._append_line(record)
        return checkpoint_id

    async def append_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read_input_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
        *,
        last_usage: UsageSnapshot | None = None,
        last_message_count: int = 0,
    ) -> None:
        """追加 _usage 行（累积值 + 最后一次调用的单次值）。

        Args:
            input_tokens: 累积 input tokens
            output_tokens: 累积 output tokens
            cache_read_input_tokens: 累积缓存命中 tokens
            cache_creation_input_tokens: 累积缓存写入 tokens
            last_usage: 最后一次 API 调用的单次用量（用于 rewind/resume 后恢复显示）
            last_message_count: 最后一次 API 调用时的消息数快照
        """
        record = {
            "role": "_usage",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
        }
        if last_usage is not None:
            record["last_input_tokens"] = last_usage.input_tokens
            record["last_output_tokens"] = last_usage.output_tokens
            record["last_cache_read_input_tokens"] = last_usage.cache_read_input_tokens
            record["last_cache_creation_input_tokens"] = (
                last_usage.cache_creation_input_tokens
            )
            record["last_message_count"] = last_message_count
        await self._append_line(record)

    async def append_message(self, message: ConversationMessage) -> None:
        """追加普通对话消息行。

        Args:
            message: 对话消息
        """
        record = {
            "role": message.role,
            "message": message.model_dump(mode="json"),
        }
        await self._append_line(record)

    async def rewind_to(self, target_checkpoint_id: int) -> RestoreResult:
        """回退到指定 checkpoint id 之前的状态。

        保留 id < target_checkpoint_id 的 _checkpoint 及其后内容，
        原地重写 context.jsonl，返回重建后的 RestoreResult。

        Args:
            target_checkpoint_id: 目标 checkpoint id（该 id 及之后内容被丢弃）

        Returns:
            RestoreResult: 重建后的内存状态
        """
        async with self._io_lock:
            if not self._file.exists():
                return RestoreResult(
                    messages=[], usage_input=0, usage_output=0,
                    usage_cache_read=0, usage_cache_creation=0,
                    last_usage=None, last_usage_message_count=0,
                    checkpoint_count=0,
                )
            # 读所有行
            kept_lines: list[str] = []
            async with aiofiles.open(self._file, encoding="utf-8") as f:
                async for line in f:
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    # 命中目标 checkpoint → 停止拷贝
                    if (
                        record.get("role") == "_checkpoint"
                        and record.get("id") == target_checkpoint_id
                    ):
                        break
                    kept_lines.append(line)
            # 原地重写
            async with aiofiles.open(self._file, "w", encoding="utf-8") as f:
                for line in kept_lines:
                    await f.write(line + "\n")
            # 重置 next_checkpoint_id 并从保留行重建
            self._next_checkpoint_id = 0
            return self._build_result_from_lines(kept_lines)

    async def restore(self) -> RestoreResult:
        """单遍扫描 context.jsonl 重建内存状态。

        旧文件中的 _system_prompt / _system_overhead 行直接跳过（不解析）。

        Returns:
            RestoreResult: 重建后的内存状态
        """
        async with self._io_lock:
            if not self._file.exists():
                return RestoreResult(
                    messages=[], usage_input=0, usage_output=0,
                    usage_cache_read=0, usage_cache_creation=0,
                    last_usage=None, last_usage_message_count=0,
                    checkpoint_count=0,
                )
            lines: list[str] = []
            async with aiofiles.open(self._file, encoding="utf-8") as f:
                async for line in f:
                    line = line.rstrip("\n")
                    if line:
                        lines.append(line)
            # 重置 next_checkpoint_id
            self._next_checkpoint_id = 0
            return self._build_result_from_lines(lines)

    async def truncate_all(self) -> None:
        """清空 context.jsonl（用于 /new）。"""
        async with self._io_lock:
            if self._file.exists():
                self._file.unlink()
            self._next_checkpoint_id = 0

    async def _append_line(self, record: dict[str, Any]) -> None:
        """加锁追加一行 JSON。第一次调用时延迟创建会话目录。"""
        async with self._io_lock:
            if not self._dir_ensured:
                self._session_dir.mkdir(parents=True, exist_ok=True)
                self._dir_ensured = True
            async with aiofiles.open(self._file, "a", encoding="utf-8") as f:
                await f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _build_result_from_lines(self, lines: list[str]) -> RestoreResult:
        """从 JSONL 行列表构建 RestoreResult（无锁，内部使用）。

        旧文件中的 _system_prompt / _system_overhead 行直接跳过（不读取）。

        Args:
            lines: JSON 字符串列表

        Returns:
            RestoreResult: 重建后的状态
        """
        messages: list[ConversationMessage] = []
        usage_input = 0
        usage_output = 0
        usage_cache_read = 0
        usage_cache_creation = 0
        last_usage: UsageSnapshot | None = None
        last_usage_message_count = 0
        checkpoint_count = 0

        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            role = record.get("role")
            if role in ("_system_prompt", "_system_overhead"):
                # 旧文件遗留行：直接跳过
                continue
            elif role == "_checkpoint":
                checkpoint_count += 1
                self._next_checkpoint_id = record.get("id", -1) + 1
            elif role == "_usage":
                usage_input = record.get("input_tokens", 0)
                usage_output = record.get("output_tokens", 0)
                usage_cache_read = record.get("cache_read_input_tokens", 0)
                usage_cache_creation = record.get("cache_creation_input_tokens", 0)
                # 最后一次 API 调用的单次分项（rewind/resume 后恢复 StatusBar 显示）
                if "last_input_tokens" in record:
                    last_usage = UsageSnapshot(
                        input_tokens=record.get("last_input_tokens", 0),
                        output_tokens=record.get("last_output_tokens", 0),
                        cache_read_input_tokens=record.get(
                            "last_cache_read_input_tokens", 0
                        ),
                        cache_creation_input_tokens=record.get(
                            "last_cache_creation_input_tokens", 0
                        ),
                    )
                    last_usage_message_count = record.get("last_message_count", 0)
            elif role in ("user", "assistant"):
                msg_data = record.get("message")
                if msg_data:
                    try:
                        messages.append(ConversationMessage.model_validate(msg_data))
                    except (ValidationError, ValueError, TypeError) as e:
                        # 损坏的消息行跳过，避免影响整次 restore
                        logging.getLogger(__name__).warning(
                            "跳过损坏的 %s 消息行: %s", role, e
                        )

        return RestoreResult(
            messages=messages,
            usage_input=usage_input,
            usage_output=usage_output,
            usage_cache_read=usage_cache_read,
            usage_cache_creation=usage_cache_creation,
            last_usage=last_usage,
            last_usage_message_count=last_usage_message_count,
            checkpoint_count=checkpoint_count,
        )
