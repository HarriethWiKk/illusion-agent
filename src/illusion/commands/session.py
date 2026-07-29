"""
会话管理斜杠命令
================

/new, /compact, /rewind, /context, /summary, /resume, /delete
"""

from __future__ import annotations

from illusion.api.errors import IllusionAgentApiError
from illusion.commands.types import CommandContext, CommandResult
from illusion.config.settings import load_settings, save_settings
from illusion.engine.messages import ConversationMessage
from illusion.prompts import build_runtime_system_prompt
from illusion.services import (
    estimate_conversation_tokens,
    get_context_window,
    summarize_messages,
)


async def new_handler(_: str, context: CommandContext) -> CommandResult:
    """启动新会话。

    不保存当前会话（每轮已 checkpoint），不清空 checkpoint 目录。
    full_reset 清空所有内存状态，由 runtime 生成新 session_id。
    """
    context.engine.full_reset()
    return CommandResult(
        message="Started a new conversation session.",
        clear_screen=True,
        reset_session=True,
        refresh_state=True,
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
        system_tokens = context.engine.overhead_tracker.tokens
        messages_tokens = estimate_conversation_tokens(context.engine.messages)
        estimated_used = (system_tokens or 0) + messages_tokens
        usage = context.engine.total_usage
        context_window = get_context_window()
        percentage = round(estimated_used * 100 / context_window) if context_window > 0 else 0
        remaining = max(0, context_window - estimated_used)
        system_pct = round(system_tokens * 100 / context_window) if (system_tokens and context_window > 0) else 0
        messages_pct = round(messages_tokens * 100 / context_window) if context_window > 0 else 0
        system_line = (
            f"  System Prompt: ~{system_tokens:,} tokens ({system_pct}%)"
            if system_tokens is not None
            else "  System Prompt: ~ tokens"
        )
        return CommandResult(
            message=(
                f"✻ Context Window: {context_window:,} tokens\n"
                f"{system_line}\n"
                f"  Messages: ~{messages_tokens:,} tokens ({messages_pct}%)\n"
                f"  Estimated Used: ~{estimated_used:,} tokens ({percentage}%)\n"
                f"  Remaining: ~{remaining:,} tokens\n"
                f"  Cumulative API Usage: input={usage.input_tokens:,} output={usage.output_tokens:,}\n"
                f"  Note: System Prompt includes skills/hooks/rules/memory/channels and other system-level overhead"
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
    except (IllusionAgentApiError, OSError, ValueError, KeyError, RuntimeError) as exc:
        import logging
        logging.getLogger(__name__).warning("LLM compact failed, falling back to simple compact: %s", exc)
        compacted = compact_messages(context.engine.messages, preserve_recent=preserve_recent)

    context.engine.load_messages(compacted)
    after_tokens = estimate_conversation_tokens(compacted)
    saved = max(0, before_tokens - after_tokens)
    from illusion.config.i18n import t
    return CommandResult(
        message=t("compact_result", before=before, after=len(compacted), saved=f"{saved:,}"),
        refresh_state=True,
    )


async def resume_handler(args: str, context: CommandContext) -> CommandResult:
    """恢复已保存的会话。

    通过 CheckpointStore.restore() 单遍扫描 context.jsonl 重建完整状态。
    """
    from illusion.services.checkpoint_store import CheckpointStore
    from illusion.services.session_storage import (
        get_project_session_dir,
        list_session_snapshots,
        read_index,
        read_meta,
        write_index,
    )

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

        # 校验 session_id 合法性（防路径遍历）
        from illusion.services.session_storage import InvalidSessionIdError
        try:
            # 读 meta.json 验证存在
            meta = read_meta(context.cwd, sid)
        except InvalidSessionIdError:
            return CommandResult(message=f"Invalid session id: {sid}")
        if meta is None:
            return CommandResult(message=f"Session not found: {sid}")

        # 构造 CheckpointStore 并 restore
        session_dir = get_project_session_dir(context.cwd) / sid
        store = CheckpointStore(session_dir, sid)
        result = await store.restore()

        # 应用到 engine
        context.engine.set_checkpoint_store(store)
        context.engine.set_session_id(sid)
        context.engine.apply_restore(result)

        # 更新 index.json
        write_index(context.cwd, sid)

        summary = meta.get("summary", "")[:60]
        return CommandResult(
            message=f"Restored {len(result.messages)} messages from session {sid}"
            + (f" ({summary})" if summary else ""),
            replay_messages=result.messages,
            restored_session_id=sid,
            refresh_state=True,
            clear_screen=True,
        )

    # /resume — 列出会话或加载 latest
    sessions = list_session_snapshots(context.cwd, limit=10)
    if not sessions:
        return CommandResult(message="No saved sessions found for this project.")

    # 无参时读 index.json 获取 latest
    index = read_index(context.cwd)
    if index is None:
        # 无 index 则列出会话供选择
        import time
        lines = ["Saved sessions:"]
        for i, s in enumerate(sessions, 1):
            ts = time.strftime("%m/%d %H:%M", time.localtime(s.get("updated_at", s.get("created_at", 0))))
            summary = s["summary"][:50] or "(no summary)"
            turn_count = s.get("turn_count", 0)
            lines.append(f"  #{i}  {s['session_id']}  {ts}  {turn_count}轮  {summary}")
        lines.append("")
        lines.append("Usage: /resume #1 or /resume <session_id>")
        return CommandResult(message="\n".join(lines))

    # 有 index 直接恢复 latest
    sid = index.get("latest_session_id", "")
    if not sid:
        return CommandResult(message="No latest session in index.")

    meta = read_meta(context.cwd, sid)
    if meta is None:
        return CommandResult(message=f"Latest session {sid} not found.")

    session_dir = get_project_session_dir(context.cwd) / sid
    store = CheckpointStore(session_dir, sid)
    result = await store.restore()
    context.engine.set_checkpoint_store(store)
    context.engine.set_session_id(sid)
    context.engine.apply_restore(result)
    write_index(context.cwd, sid)

    summary = meta.get("summary", "")[:60]
    return CommandResult(
        message=f"Restored {len(result.messages)} messages from the latest session."
        + (f" ({summary})" if summary else ""),
        replay_messages=result.messages,
        restored_session_id=sid,
        refresh_state=True,
        clear_screen=True,
    )


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

    store = context.engine.checkpoint_store
    if store is None or store.next_checkpoint_id == 0:
        return CommandResult(message="No checkpoint to rewind.")

    target_id = store.next_checkpoint_id - turns
    if target_id < 0:
        return CommandResult(
            message=f"Cannot rewind {turns} turns, only {store.next_checkpoint_id} available."
        )

    removed = 0
    restored_messages: list[ConversationMessage] | None = None

    # 回退对话
    if mode in ("both", "conversation"):
        result = await store.rewind_to(target_id)
        context.engine.apply_restore(result)
        removed = turns  # 简化：回退的 turn 数
        restored_messages = result.messages

    # 回退文件
    reverted_count = 0
    if mode in ("both", "code"):
        fh = context.engine.file_history
        if fh is not None and fh.snapshots:
            from illusion.services.file_history import rewind_to
            target_index = max(0, len(fh.snapshots) - turns)
            reverted_files = rewind_to(fh, target_index)
            reverted_count = len(reverted_files)

    lines = []
    if removed > 0:
        lines.append(f"Rewound {turns} turn(s); removed {removed} message(s).")
    if reverted_count > 0:
        lines.append(f"Reverted {reverted_count} file(s).")
    if not lines:
        lines.append("Nothing to rewind.")

    return CommandResult(
        clear_screen=True,
        replay_messages=restored_messages if mode in ("both", "conversation") else None,
        message="\n".join(lines),
        refresh_state=True,
    )


async def delete_handler(args: str, context: CommandContext) -> CommandResult:
    """删除已保存的会话（rmtree 整个 {sid}/ 目录）"""
    from illusion.services.file_history import cleanup_all_file_histories, cleanup_file_history
    from illusion.services.session_storage import (
        delete_all_sessions,
        delete_session_by_id,
        list_session_snapshots,
    )

    tokens = args.strip().split()

    # /delete — 列出会话
    if not tokens:
        sessions = list_session_snapshots(context.cwd, limit=10)
        if not sessions:
            return CommandResult(message="No saved sessions found for this project.")
        import time
        lines = ["Saved sessions:"]
        for i, s in enumerate(sessions, 1):
            ts = time.strftime("%m/%d %H:%M", time.localtime(s.get("updated_at", s.get("created_at", 0))))
            summary = s["summary"][:50] or "(no summary)"
            turn_count = s.get("turn_count", 0)
            lines.append(f"  #{i}  {s['session_id']}  {ts}  {turn_count}轮  {summary}")
        lines.append("")
        lines.append("Usage: /delete #1 or /delete <session_id>  — delete a specific session")
        lines.append("       /delete all                        — delete all sessions")
        return CommandResult(message="\n".join(lines))

    # /delete all
    if tokens[0] in ("all", "__all__"):
        count = delete_all_sessions(context.cwd)
        cleanup_all_file_histories()
        context.engine.full_reset()
        return CommandResult(
            message=f"Deleted {count} session(s).",
            clear_screen=True,
            reset_session=True,
            refresh_state=True,
        )

    # /delete <session_id> or /delete #<turn_number>
    sid = tokens[0]
    if sid.startswith("#") and sid[1:].isdigit():
        turn_num = int(sid[1:])
        sessions = list_session_snapshots(context.cwd, limit=20)
        if 1 <= turn_num <= len(sessions):
            sid = sessions[turn_num - 1]["session_id"]
        else:
            return CommandResult(message=f"Invalid turn number: {sid}. Use /delete to see available sessions.")
    # 校验 session_id 合法性（防路径遍历）
    from illusion.services.session_storage import InvalidSessionIdError
    try:
        deleted = delete_session_by_id(context.cwd, sid)
    except InvalidSessionIdError:
        return CommandResult(message=f"Invalid session id: {sid}")
    if deleted:
        cleanup_file_history(sid)
        if sid == context.session_id:
            context.engine.full_reset()
            return CommandResult(
                message=f"Deleted current session: {sid}",
                clear_screen=True,
                reset_session=True,
                refresh_state=True,
            )
        return CommandResult(message=f"Deleted session: {sid}")
    return CommandResult(message=f"Session not found: {sid}")
