"""
会话管理斜杠命令
================

/new, /compact, /rewind, /context, /summary, /resume, /delete
"""

from __future__ import annotations

from illusion.commands.helpers import rewind_turns
from illusion.commands.types import CommandContext, CommandResult
from illusion.config.settings import load_settings, save_settings
from illusion.engine.messages import ConversationMessage
from illusion.prompts import build_runtime_system_prompt
from illusion.services import estimate_conversation_tokens, save_session_snapshot, summarize_messages


async def new_handler(_: str, context: CommandContext) -> CommandResult:
    """启动新会话"""
    if context.session_id and context.engine.messages:
        settings = load_settings()
        system_prompt = build_runtime_system_prompt(settings, cwd=context.cwd, channel_hint=context.channel_hint)
        save_session_snapshot(
            cwd=context.cwd,
            model=settings.active_model_name,
            system_prompt=system_prompt,
            messages=context.engine.messages,
            usage=context.engine.total_usage,
            session_id=context.session_id,
        )
    context.engine.clear()
    return CommandResult(
        message="Started a new conversation session.",
        clear_screen=True,
        reset_session=True,
    )


async def status_handler(_: str, context: CommandContext) -> CommandResult:
    """显示会话状态"""
    usage = context.engine.total_usage
    state = context.app_state.get() if context.app_state is not None else None
    return CommandResult(
        message=(
            f"Messages: {len(context.engine.messages)}\n"
            f"Usage: input={usage.input_tokens} output={usage.output_tokens}\n"
            f"Effort: {state.effort if state is not None else load_settings().effort}\n"
            f"Passes: {state.passes if state is not None else load_settings().passes}"
        )
    )


async def context_handler(args: str, context: CommandContext) -> CommandResult:
    """显示上下文使用量、系统提示词或管理上下文窗口"""
    settings = load_settings()
    tokens = args.split(maxsplit=1)
    subcommand = tokens[0] if tokens else "usage"

    if subcommand in ("usage", "__usage__"):
        from illusion.services.compact import estimate_conversation_tokens, get_context_window
        estimated = estimate_conversation_tokens(context.engine.messages)
        usage = context.engine.total_usage
        context_window = get_context_window(settings.active_model_name)
        percentage = int(estimated * 100 / context_window) if context_window > 0 else 0
        remaining = max(0, context_window - estimated)
        return CommandResult(
            message=(
                f"Context Window: {context_window:,} tokens\n"
                f"Estimated Used: ~{estimated:,} tokens ({percentage}%)\n"
                f"Remaining: ~{remaining:,} tokens\n"
                f"Actual API Usage: input={usage.input_tokens:,} output={usage.output_tokens:,}\n"
                f"Messages: {len(context.engine.messages)}"
            )
        )
    if subcommand == "show":
        # 显示当前运行时完整的系统提示词
        system_prompt = context.engine._system_prompt
        return CommandResult(message=system_prompt or "(no system prompt)")
    if subcommand == "window":
        return CommandResult(message=f"Context window: {settings.context_window:,} tokens")
    if subcommand == "set" and len(tokens) == 2:
        try:
            value = int(tokens[1])
            if value <= 0:
                return CommandResult(message="Error: context window must be positive")
            settings.context_window = value
            save_settings(settings)
            return CommandResult(message=f"Context window set to {value:,} tokens")
        except ValueError:
            return CommandResult(message="Error: invalid number")
    return CommandResult(message="Usage: /context [usage|show|window|set N]")


async def summary_handler(args: str, context: CommandContext) -> CommandResult:
    """总结对话历史"""
    max_messages = 8
    if args:
        try:
            max_messages = max(1, int(args))
        except ValueError:
            return CommandResult(message="Usage: /summary [MAX_MESSAGES]")
    summary = summarize_messages(context.engine.messages, max_messages=max_messages)
    return CommandResult(message=summary or "No conversation content to summarize.")


async def compact_handler(args: str, context: CommandContext) -> CommandResult:
    """压缩对话历史"""
    from illusion.services.compact import compact_conversation, compact_messages

    preserve_recent = 6
    custom_instructions: str | None = None

    if args:
        stripped = args.strip()
        try:
            preserve_recent = max(1, int(stripped))
        except ValueError:
            custom_instructions = stripped

    before = len(context.engine.messages)
    before_tokens = estimate_conversation_tokens(context.engine.messages)

    try:
        settings = load_settings()
        system_prompt = build_runtime_system_prompt(settings, cwd=context.cwd, channel_hint=context.channel_hint)
        compacted = await compact_conversation(
            context.engine.messages,
            api_client=context.engine._api_client,
            model=context.engine._model,
            system_prompt=system_prompt,
            preserve_recent=preserve_recent,
            custom_instructions=custom_instructions,
            suppress_follow_up=False,
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("LLM compact failed, falling back to simple compact: %s", exc)
        compacted = compact_messages(context.engine.messages, preserve_recent=preserve_recent)

    context.engine.load_messages(compacted)
    after_tokens = estimate_conversation_tokens(compacted)
    saved = max(0, before_tokens - after_tokens)
    from illusion.config.i18n import t
    return CommandResult(
        message=t("compact_result", before=before, after=len(compacted), saved=f"{saved:,}")
    )


async def resume_handler(args: str, context: CommandContext) -> CommandResult:
    """恢复已保存的会话"""
    from illusion.services.session_storage import list_session_snapshots, load_session_by_id

    tokens = args.strip().split()

    # /resume <session_id> or /resume #<turn_number>
    if tokens:
        sid = tokens[0]
        # 支持轮次编号引用（如 #1, #2）
        if sid.startswith("#") and sid[1:].isdigit():
            turn_num = int(sid[1:])
            sessions = list_session_snapshots(context.cwd, limit=20)
            if 1 <= turn_num <= len(sessions):
                sid = sessions[turn_num - 1]["session_id"]
            else:
                return CommandResult(message=f"Invalid turn number: {sid}. Use /resume to see available sessions.")
        snapshot = load_session_by_id(context.cwd, sid)
        if snapshot is None:
            return CommandResult(message=f"Session not found: {sid}")
        messages = [
            ConversationMessage.model_validate(item)
            for item in snapshot.get("messages", [])
        ]
        context.engine.load_messages(messages)
        summary = snapshot.get("summary", "")[:60]
        return CommandResult(
            message=f"Restored {len(messages)} messages from session {sid}"
            + (f" ({summary})" if summary else ""),
            replay_messages=messages,
            restored_session_id=str(snapshot.get("session_id") or sid),
        )

    # /resume — 列出会话
    sessions = list_session_snapshots(context.cwd, limit=10)
    if not sessions:
        from illusion.services.session_storage import load_session_snapshot
        snapshot = load_session_snapshot(context.cwd)
        if snapshot is None:
            return CommandResult(message="No saved sessions found for this project.")
        messages = [
            ConversationMessage.model_validate(item)
            for item in snapshot.get("messages", [])
        ]
        context.engine.load_messages(messages)
        return CommandResult(
            message=f"Restored {len(messages)} messages from the latest session.",
            replay_messages=messages,
            restored_session_id=str(snapshot.get("session_id", "")),
        )

    import time
    lines = ["Saved sessions:"]
    for i, s in enumerate(sessions, 1):
        ts = time.strftime("%m/%d %H:%M", time.localtime(s["created_at"]))
        summary = s["summary"][:50] or "(no summary)"
        turn_count = s.get("turn_count", 0)
        lines.append(f"  #{i}  {s['session_id']}  {ts}  {turn_count}轮  {summary}")
    lines.append("")
    lines.append("Usage: /resume #1 or /resume <session_id>")
    return CommandResult(message="\n".join(lines))


async def rewind_handler(args: str, context: CommandContext) -> CommandResult:
    """回退对话回合

    支持三种模式：
    - both（默认）：同时回退对话和文件
    - conversation：仅回退对话
    - code：仅回退文件修改

    用法：/rewind [TURNS] [both|conversation|code]
    """
    parts = args.strip().split()
    turns = 1
    mode = "both"
    if parts:
        try:
            turns = max(1, int(parts[0]))
        except ValueError:
            return CommandResult(message="Usage: /rewind [TURNS] [both|conversation|code]")
        if len(parts) > 1:
            mode = parts[1].lower()
            if mode not in ("both", "conversation", "code"):
                return CommandResult(message="Usage: /rewind [TURNS] [both|conversation|code]")

    # 回退对话
    removed = 0
    updated = context.engine.messages
    if mode in ("both", "conversation"):
        before = len(context.engine.messages)
        updated = rewind_turns(context.engine.messages, turns)
        removed = before - len(updated)

    # 回退文件
    reverted_count = 0
    if mode in ("both", "code"):
        fh = context.engine.file_history
        if fh is not None and fh.snapshots:
            from illusion.services.file_history import rewind_to
            target_index = max(0, len(fh.snapshots) - turns)
            reverted_files = rewind_to(fh, target_index)
            reverted_count = len(reverted_files)

    # 应用对话变更
    if mode in ("both", "conversation"):
        context.engine.load_messages(updated)

    lines = []
    if removed > 0:
        lines.append(f"Rewound {turns} turn(s); removed {removed} message(s).")
    if reverted_count > 0:
        lines.append(f"Reverted {reverted_count} file(s).")
    if not lines:
        lines.append("Nothing to rewind.")

    return CommandResult(
        clear_screen=True,
        replay_messages=list(updated) if mode in ("both", "conversation") else None,
        message="\n".join(lines),
    )


async def delete_handler(args: str, context: CommandContext) -> CommandResult:
    """删除已保存的会话"""
    from illusion.services.session_storage import (
        delete_all_sessions,
        delete_session_by_id,
        list_session_snapshots,
    )
    from illusion.services.file_history import cleanup_file_history, cleanup_all_file_histories

    tokens = args.strip().split()

    # /delete — 列出会话
    if not tokens:
        sessions = list_session_snapshots(context.cwd, limit=10)
        if not sessions:
            return CommandResult(message="No saved sessions found for this project.")
        import time
        lines = ["Saved sessions:"]
        for i, s in enumerate(sessions, 1):
            ts = time.strftime("%m/%d %H:%M", time.localtime(s["created_at"]))
            summary = s["summary"][:50] or "(no summary)"
            turn_count = s.get("turn_count", 0)
            lines.append(f"  #{i}  {s['session_id']}  {ts}  {turn_count}轮  {summary}")
        lines.append("")
        lines.append("Usage: /delete #1 or /delete <session_id>  — delete a specific session")
        lines.append("       /delete all                        — delete all sessions")
        return CommandResult(message="\n".join(lines))

    # /delete all
    # 注意：此操作仅删除终端侧会话快照，不再跨进程通知渠道守护进程清空渠道会话。
    # 渠道会话由渠道自身的 /clear、/new 命令管理（信号机制已全链路移除）。
    if tokens[0] in ("all", "__all__"):
        count = delete_all_sessions(context.cwd)
        cleanup_all_file_histories()
        context.engine.clear()
        return CommandResult(
            message=f"Deleted {count} session file(s).",
            clear_screen=True,
            reset_session=True,
        )

    # /delete <session_id> or /delete #<turn_number>
    sid = tokens[0]
    # 支持轮次编号引用（如 #1, #2）
    if sid.startswith("#") and sid[1:].isdigit():
        turn_num = int(sid[1:])
        sessions = list_session_snapshots(context.cwd, limit=20)
        if 1 <= turn_num <= len(sessions):
            sid = sessions[turn_num - 1]["session_id"]
        else:
            return CommandResult(message=f"Invalid turn number: {sid}. Use /delete to see available sessions.")
    if delete_session_by_id(context.cwd, sid):
        cleanup_file_history(sid)
        if sid == context.session_id:
            context.engine.clear()
            return CommandResult(
                message=f"Deleted current session: {sid}",
                clear_screen=True,
                reset_session=True,
            )
        return CommandResult(message=f"Deleted session: {sid}")
    return CommandResult(message=f"Session not found: {sid}")
