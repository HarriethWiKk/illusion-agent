"""
Bridge 斜杠命令
===============

/bridge — 管理 bridge 会话
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from illusion.bridge import get_bridge_manager
from illusion.bridge.types import WorkSecret
from illusion.bridge.work_secret import build_sdk_url, decode_work_secret, encode_work_secret
from illusion.commands.types import CommandContext, CommandResult


async def bridge_handler(args: str, context: CommandContext) -> CommandResult:
    """Bridge 命令处理器

    子命令：show, encode, decode, sdk, spawn, list, output, stop
    """
    tokens = args.split()
    if not tokens or tokens[0] == "show":
        sessions = get_bridge_manager().list_sessions()
        lines = [
            "Bridge summary:",
            "- backend host: available",
            f"- cwd: {context.cwd}",
            f"- sessions: {len(sessions)}",
            "- utilities: encode, decode, sdk, spawn, list, output, stop",
        ]
        return CommandResult(message="\n".join(lines))
    if tokens[0] == "encode" and len(tokens) == 3:
        encoded = encode_work_secret(
            WorkSecret(version=1, session_ingress_token=tokens[2], api_base_url=tokens[1])
        )
        return CommandResult(message=encoded)
    if tokens[0] == "decode" and len(tokens) == 2:
        secret = decode_work_secret(tokens[1])
        return CommandResult(message=json.dumps(secret.__dict__, indent=2))
    if tokens[0] == "sdk" and len(tokens) == 3:
        return CommandResult(message=build_sdk_url(tokens[1], tokens[2]))
    if tokens[0] == "spawn" and len(tokens) >= 2:
        command = args[len("spawn "):]
        handle = await get_bridge_manager().spawn(
            session_id=f"bridge-{datetime.now(UTC).strftime('%H%M%S')}",
            command=command,
            cwd=context.cwd,
        )
        return CommandResult(
            message=f"Spawned bridge session {handle.session_id} pid={handle.process.pid}"
        )
    if tokens[0] == "list":
        sessions = get_bridge_manager().list_sessions()
        if not sessions:
            return CommandResult(message="No bridge sessions.")
        return CommandResult(
            message="\n".join(
                f"{item.session_id} [{item.status}] pid={item.pid} {item.command}"
                for item in sessions
            )
        )
    if tokens[0] == "output" and len(tokens) == 2:
        return CommandResult(message=get_bridge_manager().read_output(tokens[1]) or "(no output)")
    if tokens[0] == "stop" and len(tokens) == 2:
        try:
            await get_bridge_manager().stop(tokens[1])
        except ValueError as exc:
            return CommandResult(message=str(exc))
        return CommandResult(message=f"Stopped bridge session {tokens[1]}")
    return CommandResult(
        message="Usage: /bridge [show|encode API_BASE_URL TOKEN|decode SECRET|sdk API_BASE_URL SESSION_ID|spawn CMD|list|output SESSION_ID|stop SESSION_ID]"
    )
