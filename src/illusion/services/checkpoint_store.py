"""Checkpoint 持久化存储。

基于单文件 JSONL append-only 模式，5 种 role 行：
_system_prompt / _checkpoint / _usage / _system_overhead / 普通消息。
rewind 原地重写，restore 单遍扫描重建内存状态。

主要类：
    - RestoreResult: restore 结果数据类
    - CheckpointStore: context.jsonl 读写管理器
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import aiofiles

from illusion.engine.messages import ConversationMessage


@dataclass
class RestoreResult:
    """CheckpointStore.restore() 的结果。

    Attributes:
        messages: 重建的对话消息列表
        usage_input: 最后一个 _usage 的 input_tokens
        usage_output: 最后一个 _usage 的 output_tokens
        system_overhead: 最后一个 _system_overhead 的 tokens
        system_overhead_hash: 最后一个 _system_overhead 的 prompt_hash
        system_prompt: 最后一个 _system_prompt 的 content
        system_prompt_hash: 最后一个 _system_prompt 的 hash
        checkpoint_count: _checkpoint 行数（用于 rewind 计数）
    """
    messages: list[ConversationMessage]
    usage_input: int
    usage_output: int
    system_overhead: int | None
    system_overhead_hash: str | None
    system_prompt: str | None
    system_prompt_hash: str | None
    checkpoint_count: int


class CheckpointStore:
    """context.jsonl 的 append-only 持久化存储。

    单文件 JSONL，含 5 种 role：_system_prompt / _checkpoint /
    _usage / _system_overhead / 普通消息。append-only 保证崩溃安全，
    rewind 通过原地重写实现。

    Attributes:
        next_checkpoint_id: 下一个 _checkpoint 的 id（单调递增）
    """

    def __init__(self, session_dir: Path, session_id: str) -> None:
        """初始化 CheckpointStore。

        Args:
            session_dir: 会话目录（含 context.jsonl）
            session_id: 会话 ID
        """
        self._session_dir = session_dir
        self._session_id = session_id
        self._file = session_dir / "context.jsonl"
        self._io_lock = asyncio.Lock()
        self._next_checkpoint_id = 0

    @property
    def next_checkpoint_id(self) -> int:
        """返回下一个 checkpoint id。"""
        return self._next_checkpoint_id

    @property
    def session_id(self) -> str:
        """返回会话 ID。"""
        return self._session_id

    async def append_system_prompt(self, content: str, hash_: str) -> None:
        """追加 _system_prompt 行。

        Args:
            content: system prompt 文本
            hash_: system prompt 的 sha256 哈希
        """
        record = {"role": "_system_prompt", "content": content, "hash": hash_}
        await self._append_line(record)

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

    async def append_usage(self, input_tokens: int, output_tokens: int) -> None:
        """追加 _usage 行（累积值）。

        Args:
            input_tokens: 累积 input tokens
            output_tokens: 累积 output tokens
        """
        record = {
            "role": "_usage",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        await self._append_line(record)

    async def append_system_overhead(self, tokens: int, prompt_hash: str) -> None:
        """追加 _system_overhead 行。

        Args:
            tokens: 实测 system overhead tokens
            prompt_hash: 对应的 system prompt 哈希
        """
        record = {
            "role": "_system_overhead",
            "tokens": tokens,
            "prompt_hash": prompt_hash,
        }
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
                    system_overhead=None, system_overhead_hash=None,
                    system_prompt=None, system_prompt_hash=None,
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

        Returns:
            RestoreResult: 重建后的内存状态
        """
        async with self._io_lock:
            if not self._file.exists():
                return RestoreResult(
                    messages=[], usage_input=0, usage_output=0,
                    system_overhead=None, system_overhead_hash=None,
                    system_prompt=None, system_prompt_hash=None,
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

    async def _append_line(self, record: dict) -> None:
        """加锁追加一行 JSON。"""
        async with self._io_lock:
            self._session_dir.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(self._file, "a", encoding="utf-8") as f:
                await f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _build_result_from_lines(self, lines: list[str]) -> RestoreResult:
        """从 JSONL 行列表构建 RestoreResult（无锁，内部使用）。

        Args:
            lines: JSON 字符串列表

        Returns:
            RestoreResult: 重建后的状态
        """
        messages: list[ConversationMessage] = []
        usage_input = 0
        usage_output = 0
        system_overhead: int | None = None
        system_overhead_hash: str | None = None
        system_prompt: str | None = None
        system_prompt_hash: str | None = None
        checkpoint_count = 0

        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            role = record.get("role")
            if role == "_system_prompt":
                system_prompt = record.get("content")
                system_prompt_hash = record.get("hash")
            elif role == "_checkpoint":
                checkpoint_count += 1
                self._next_checkpoint_id = record.get("id", -1) + 1
            elif role == "_usage":
                usage_input = record.get("input_tokens", 0)
                usage_output = record.get("output_tokens", 0)
            elif role == "_system_overhead":
                system_overhead = record.get("tokens")
                system_overhead_hash = record.get("prompt_hash")
            elif role in ("user", "assistant"):
                msg_data = record.get("message")
                if msg_data:
                    try:
                        messages.append(ConversationMessage.model_validate(msg_data))
                    except Exception:
                        pass

        return RestoreResult(
            messages=messages,
            usage_input=usage_input,
            usage_output=usage_output,
            system_overhead=system_overhead,
            system_overhead_hash=system_overhead_hash,
            system_prompt=system_prompt,
            system_prompt_hash=system_prompt_hash,
            checkpoint_count=checkpoint_count,
        )
