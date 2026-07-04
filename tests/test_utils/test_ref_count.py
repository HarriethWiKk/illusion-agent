"""引用计数工具测试"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from illusion.utils.ref_count import (
    add_ref,
    alive_refs,
    ref_monitor_loop,
    remove_ref,
)


def test_add_ref_creates_file(tmp_path: Path):
    """首次 add_ref 创建文件并写入 PID"""
    refs = tmp_path / "test.refs"
    add_ref(refs, 12345)
    assert refs.read_text(encoding="utf-8").strip() == "12345"


def test_add_ref_dedup(tmp_path: Path):
    """重复 add_ref 同一 PID 不重复"""
    refs = tmp_path / "test.refs"
    add_ref(refs, 12345)
    add_ref(refs, 12345)
    assert refs.read_text(encoding="utf-8").strip() == "12345"


def test_add_ref_multiple(tmp_path: Path):
    """多个 PID 逐行存储"""
    refs = tmp_path / "test.refs"
    add_ref(refs, 100)
    add_ref(refs, 200)
    add_ref(refs, 300)
    text = refs.read_text(encoding="utf-8")
    assert "100" in text and "200" in text and "300" in text
    assert len(text.strip().splitlines()) == 3


def test_remove_ref(tmp_path: Path):
    """remove_ref 移除指定 PID"""
    refs = tmp_path / "test.refs"
    add_ref(refs, 100)
    add_ref(refs, 200)
    remove_ref(refs, 100)
    pids = refs.read_text(encoding="utf-8").strip().splitlines()
    assert "100" not in pids
    assert "200" in pids


def test_remove_ref_missing_pid_silent(tmp_path: Path):
    """remove_ref 不存在的 PID 静默"""
    refs = tmp_path / "test.refs"
    add_ref(refs, 100)
    # 不抛异常
    remove_ref(refs, 99999)


def test_remove_ref_missing_file_silent(tmp_path: Path):
    """remove_ref 文件不存在时静默"""
    refs = tmp_path / "missing.refs"
    # 不抛异常
    remove_ref(refs, 100)


def test_alive_refs_cleans_dead_pids(tmp_path: Path):
    """alive_refs 清理死 PID 并返回存活列表"""
    refs = tmp_path / "test.refs"
    current_pid = os.getpid()
    dead_pid = 0xFFFFFFFF  # 几乎不可能存在
    add_ref(refs, current_pid)
    add_ref(refs, dead_pid)

    alive = alive_refs(refs)
    assert current_pid in alive
    assert dead_pid not in alive
    # 文件应已更新（清理死 PID）
    text = refs.read_text(encoding="utf-8")
    assert str(dead_pid) not in text


def test_alive_refs_empty_file(tmp_path: Path):
    """alive_refs 文件不存在时返回空列表"""
    refs = tmp_path / "missing.refs"
    assert alive_refs(refs) == []


def test_alive_refs_only_dead(tmp_path: Path):
    """全部为死 PID 时返回空列表并清空文件"""
    refs = tmp_path / "test.refs"
    add_ref(refs, 0xFFFFFFFF)
    assert alive_refs(refs) == []
    # 文件应为空或仅含空白
    assert refs.read_text(encoding="utf-8").strip() == ""


@pytest.mark.asyncio
async def test_ref_monitor_loop_empty_triggers_stop(tmp_path: Path):
    """refs 为空时 ref_monitor_loop 触发 stop_event"""
    refs = tmp_path / "test.refs"
    add_ref(refs, 0xFFFFFFFF)  # 死 PID

    stop_event = asyncio.Event()
    # 用 1s 间隔加快测试
    task = asyncio.create_task(
        ref_monitor_loop(stop_event, refs, interval=0)
    )
    # 等待 stop_event 被触发
    await asyncio.wait_for(stop_event.wait(), timeout=2.0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_ref_monitor_loop_alive_keeps_running(tmp_path: Path):
    """refs 含存活 PID 时 ref_monitor_loop 不触发 stop"""
    refs = tmp_path / "test.refs"
    add_ref(refs, os.getpid())  # 当前进程

    stop_event = asyncio.Event()
    task = asyncio.create_task(
        ref_monitor_loop(stop_event, refs, interval=0)
    )
    # 等待 0.5s，stop_event 不应被触发
    await asyncio.sleep(0.5)
    assert not stop_event.is_set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
