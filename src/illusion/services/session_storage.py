"""
会话持久化辅助模块
================

本模块提供会话状态持久化功能，支持保存和加载会话快照。

主要功能：
    - 获取项目会话目录
    - 保存会话快照
    - 加载会话快照
    - 列出会话快照
    - 导出会话记录为 Markdown

类说明：
    - get_project_session_dir: 获取项目会话目录
    - save_session_snapshot: 保存会话快照
    - load_session_snapshot: 加载会话快照
    - list_session_snapshots: 列出会话快照
    - export_session_markdown: 导出为 Markdown

使用示例：
    >>> from illusion.services.session_storage import get_project_session_dir, save_session_snapshot
    >>> # 获取项目会话目录
    >>> session_dir = get_project_session_dir("/path/to/project")
    >>> # 保存会话快照
    >>> save_session_snapshot(cwd="/path/to/project", model="claude-3", messages=[...], usage=...)
"""

from __future__ import annotations

import json
import time
from hashlib import sha1
from pathlib import Path
from typing import Any
from uuid import uuid4

from illusion.api.usage import UsageSnapshot
from illusion.config.paths import get_sessions_dir
from illusion.engine.messages import ConversationMessage
from illusion.utils.atomic_write import atomic_write_text


def get_project_session_dir(cwd: str | Path) -> Path:
    """返回项目的会话目录。"""
    path = Path(cwd).resolve()
    # 使用路径的 SHA1 哈希前 12 位作为目录名的一部分
    digest = sha1(str(path).encode("utf-8")).hexdigest()[:12]
    session_dir = get_sessions_dir() / f"{path.name}-{digest}"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def save_session_snapshot(
    *,
    cwd: str | Path,
    model: str,
    system_prompt: str,
    messages: list[ConversationMessage],
    usage: UsageSnapshot,
    session_id: str | None = None,
) -> Path:
    """持久化会话快照。同时按 ID 保存和保存为 latest。"""
    session_dir = get_project_session_dir(cwd)
    sid = session_id or uuid4().hex[:12]
    now = time.time()
    # 从第一个用户消息提取摘要
    summary = ""
    for msg in messages:
        if msg.role == "user" and msg.text.strip():
            summary = msg.text.strip()[:80]
            break

    payload = {
        "session_id": sid,
        "cwd": str(Path(cwd).resolve()),
        "model": model,
        "system_prompt": system_prompt,
        "messages": [message.model_dump(mode="json") for message in messages],
        "usage": usage.model_dump(),
        "created_at": now,
        "summary": summary,
        "message_count": len(messages),
    }
    data = json.dumps(payload, indent=2) + "\n"

    # 保存为 latest
    latest_path = session_dir / "latest.json"
    atomic_write_text(latest_path, data)

    # 按会话 ID 保存
    session_path = session_dir / f"session-{sid}.json"
    atomic_write_text(session_path, data)

    return latest_path


def load_session_snapshot(cwd: str | Path) -> dict[str, Any] | None:
    """加载项目的最新会话快照。"""
    path = get_project_session_dir(cwd) / "latest.json"
    if not path.exists():
        return None
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def list_session_snapshots(cwd: str | Path, limit: int = 20) -> list[dict[str, Any]]:
    """列出项目的已保存会话，按最新优先排序。"""
    session_dir = get_project_session_dir(cwd)
    sessions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # 命名会话文件
    for path in sorted(session_dir.glob("session-*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            sid = data.get("session_id", path.stem.replace("session-", ""))
            seen_ids.add(sid)
            summary = data.get("summary", "")
            if not summary:
                # 从消息中提取
                for msg in data.get("messages", []):
                    if msg.get("role") == "user":
                        texts = [b.get("text", "") for b in msg.get("content", []) if b.get("type") == "text"]
                        summary = " ".join(texts).strip()[:80]
                        if summary:
                            break
            messages = data.get("messages", [])
            sessions.append({
                "session_id": sid,
                "summary": summary,
                "message_count": data.get("message_count", len(messages)),
                "turn_count": count_turns(messages),
                "model": data.get("model", ""),
                "created_at": data.get("created_at", path.stat().st_mtime),
            })
        except (json.JSONDecodeError, OSError):
            continue
        if len(sessions) >= limit:
            break

    # 也包含 latest.json（如果没有对应的会话文件）
    latest_path = session_dir / "latest.json"
    if latest_path.exists() and len(sessions) < limit:
        try:
            data = json.loads(latest_path.read_text(encoding="utf-8"))
            sid = data.get("session_id", "latest")
            if sid not in seen_ids:
                summary = data.get("summary", "")
                if not summary:
                    for msg in data.get("messages", []):
                        if msg.get("role") == "user":
                            texts = [b.get("text", "") for b in msg.get("content", []) if b.get("type") == "text"]
                            summary = " ".join(texts).strip()[:80]
                            if summary:
                                break
                messages = data.get("messages", [])
                sessions.append({
                    "session_id": sid,
                    "summary": summary or "(latest session)",
                    "message_count": data.get("message_count", len(messages)),
                    "turn_count": count_turns(messages),
                    "model": data.get("model", ""),
                    "created_at": data.get("created_at", latest_path.stat().st_mtime),
                })
        except (json.JSONDecodeError, OSError):
            pass

    # 按 created_at 降序排序
    sessions.sort(key=lambda s: s.get("created_at", 0), reverse=True)
    return sessions[:limit]


def load_session_by_id(cwd: str | Path, session_id: str) -> dict[str, Any] | None:
    """按 ID 加载特定会话。"""
    session_dir = get_project_session_dir(cwd)
    # 先尝试命名会话
    path = session_dir / f"session-{session_id}.json"
    if path.exists():
        result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return result
    # 回退到 latest.json（如果 session_id 匹配）
    latest = session_dir / "latest.json"
    if latest.exists():
        data: dict[str, Any] = json.loads(latest.read_text(encoding="utf-8"))
        if data.get("session_id") == session_id or session_id == "latest":
            return data
    return None


def delete_session_by_id(cwd: str | Path, session_id: str) -> bool:
    """按 ID 删除特定会话。返回是否成功删除。"""
    session_dir = get_project_session_dir(cwd)
    path = session_dir / f"session-{session_id}.json"
    if path.exists():
        path.unlink()
        # 如果删除的是 latest.json 对应的会话，也删除 latest.json
        latest = session_dir / "latest.json"
        if latest.exists():
            try:
                data = json.loads(latest.read_text(encoding="utf-8"))
                if data.get("session_id") == session_id:
                    latest.unlink()
            except (json.JSONDecodeError, OSError):
                pass
        return True
    return False


def delete_all_sessions(cwd: str | Path) -> int:
    """删除项目的所有会话快照。返回删除的文件数量。"""
    session_dir = get_project_session_dir(cwd)
    count = 0
    for path in session_dir.glob("session-*.json"):
        path.unlink()
        count += 1
    latest = session_dir / "latest.json"
    if latest.exists():
        latest.unlink()
        count += 1
    return count


def export_session_markdown(
    *,
    cwd: str | Path,
    messages: list[ConversationMessage],
) -> Path:
    """将会话记录导出为 Markdown。"""
    session_dir = get_project_session_dir(cwd)
    path = session_dir / "transcript.md"
    parts: list[str] = ["# IllusionCode Session Transcript"]
    for message in messages:
        parts.append(f"\n## {message.role.capitalize()}\n")
        text = message.text.strip()
        if text:
            parts.append(text)
        for block in message.tool_uses:
            parts.append(f"\n```tool\n{block.name} {json.dumps(block.input, ensure_ascii=True)}\n```")
        for content_block in message.content:
            if getattr(content_block, "type", "") == "tool_result":
                parts.append(f"\n```tool-result\n{getattr(content_block, 'content', '')}\n```")
    atomic_write_text(path, "\n".join(parts).strip() + "\n")
    return path


def count_turns(messages: list[dict[str, Any]]) -> int:
    """统计消息列表中的轮次数

    一个轮次定义为一个非空的、非斜杠命令的用户消息。
    这与 /rewind 命令的定义一致。

    Args:
        messages: 消息列表

    Returns:
        int: 轮次数
    """
    turn_count = 0
    for msg in messages:
        if msg.get("role") == "user":
            # 获取消息文本
            text = ""
            if isinstance(msg.get("text"), str):
                text = msg["text"].strip()
            elif isinstance(msg.get("content"), list):
                # 从 content 数组中提取文本
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text += block.get("text", "")
                text = text.strip()

            # 统计非空的、非斜杠命令的用户消息
            if text and not text.startswith("/"):
                turn_count += 1

    return turn_count


# ---------------------------------------------------------------------------
# Pending Question 持久化
# ---------------------------------------------------------------------------

def _pending_question_path(cwd: str | Path, session_id: str) -> Path:
    """返回指定会话的 pending question 文件路径"""
    session_dir = get_project_session_dir(cwd)
    return session_dir / f"pending-question-{session_id}.json"


def save_pending_question(
    *,
    cwd: str | Path,
    session_id: str,
    tool_use_id: str,
    questions: list[dict[str, Any]],
    question_text: str,
) -> Path:
    """保存待回答的 ask_user_question 问题

    Args:
        cwd: 工作目录
        session_id: 会话 ID
        tool_use_id: 触发问题的 tool_use ID（用于恢复时匹配 tool_result）
        questions: 结构化问题数据（list[dict]）
        question_text: 格式化后的问题文本（用于显示给用户）

    Returns:
        Path: 持久化文件路径
    """
    payload = {
        "session_id": session_id,
        "tool_use_id": tool_use_id,
        "questions": questions,
        "question_text": question_text,
        "created_at": time.time(),
    }
    path = _pending_question_path(cwd, session_id)
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def load_pending_question(cwd: str | Path, session_id: str) -> dict[str, Any] | None:
    """加载指定会话的 pending question

    Returns:
        dict | None: 问题数据，无则 None
    """
    path = _pending_question_path(cwd, session_id)
    if not path.exists():
        return None
    try:
        result: dict[str, Any] | None = json.loads(path.read_text(encoding="utf-8"))
        return result
    except (json.JSONDecodeError, OSError):
        return None


def delete_pending_question(cwd: str | Path, session_id: str) -> bool:
    """删除指定会话的 pending question

    Returns:
        bool: 是否成功删除
    """
    path = _pending_question_path(cwd, session_id)
    if path.exists():
        path.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Pending Plan Approval 持久化
# ---------------------------------------------------------------------------

def _pending_plan_approval_path(cwd: str | Path, session_id: str) -> Path:
    """返回指定会话的 pending plan approval 文件路径"""
    session_dir = get_project_session_dir(cwd)
    return session_dir / f"pending-plan-approval-{session_id}.json"


def save_pending_plan_approval(
    *,
    cwd: str | Path,
    session_id: str,
    plan: str,
    plan_path: str,
) -> Path:
    """保存待审批的计划内容（print 模式跨轮次审批机制）

    Args:
        cwd: 工作目录
        session_id: 会话 ID
        plan: 计划内容文本
        plan_path: 计划文件路径（用于恢复时引用）

    Returns:
        Path: 持久化文件路径
    """
    payload = {
        "session_id": session_id,
        "plan": plan,
        "plan_path": plan_path,
        "created_at": time.time(),
    }
    path = _pending_plan_approval_path(cwd, session_id)
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def load_pending_plan_approval(cwd: str | Path, session_id: str) -> dict[str, Any] | None:
    """加载指定会话的 pending plan approval

    Returns:
        dict | None: 计划审批数据，无则 None
    """
    path = _pending_plan_approval_path(cwd, session_id)
    if not path.exists():
        return None
    try:
        result: dict[str, Any] | None = json.loads(path.read_text(encoding="utf-8"))
        return result
    except (json.JSONDecodeError, OSError):
        return None


def delete_pending_plan_approval(cwd: str | Path, session_id: str) -> bool:
    """删除指定会话的 pending plan approval

    Returns:
        bool: 是否成功删除
    """
    path = _pending_plan_approval_path(cwd, session_id)
    if path.exists():
        path.unlink()
        return True
    return False