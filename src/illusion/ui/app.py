"""
App 应用程序模块
=============

本模块实现 IllusionAgent 交互式会话入口点。

主要功能：
    - REPL 交互模式（默认的 React 终端界面）
    - 打印模式（非交互式，适合脚本和自动化任务）
    - 后端单独运行模式

函数说明：
    - run_repl: 运行交互式 REPL
    - run_print_mode: 运行非交互式打印模式

使用示例：
    >>> from illusion.ui.app import run_repl, run_print_mode
    >>> 
    >>> # 启动交互式 REPL
    >>> await run_repl()
    >>> 
    >>> # 运行单次交互模式
    >>> await run_print_mode(prompt="帮我写一个 hello world 程序")
"""

from __future__ import annotations

import json
import sys
from typing import Any

from illusion.api.client import SupportsStreamingMessages
from illusion.engine.stream_events import StreamEvent
from illusion.ui.backend_host import run_backend_host
from illusion.ui.react_launcher import launch_react_tui
from illusion.ui.runtime import build_runtime, close_runtime, handle_line, start_runtime
from illusion.ui.terminal_io import PENDING_ANSWER_MARKER, PENDING_PLAN_APPROVAL_MARKER


def _inject_answer_to_pending_tool_result(
    messages: list[dict[str, Any]],
    answer: str,
) -> list[dict[str, Any]]:
    """把用户答案注入到消息历史中 PENDING_ANSWER_MARKER 的 tool_result

    扫描 messages（反向），找到最后一个 content 包含 PENDING_ANSWER_MARKER
    的 tool_result block，替换其 content 为用户的答案。

    Args:
        messages: 序列化的会话消息列表
        answer: 用户的答案文本

    Returns:
        list[dict]: 修改后的消息列表（浅拷贝）
    """
    import copy
    result = copy.deepcopy(messages)
    # 反向扫描，找最后一个 PENDING_ANSWER_MARKER 的 tool_result
    for msg in reversed(result):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue
            block_content = block.get("content")
            # content 可能是 str 或 list
            if isinstance(block_content, str) and PENDING_ANSWER_MARKER in block_content:
                block["content"] = answer
                block["is_error"] = False
                return result
            if isinstance(block_content, list):
                for sub in block_content:
                    if (
                        isinstance(sub, dict)
                        and isinstance(sub.get("text"), str)
                        and PENDING_ANSWER_MARKER in sub["text"]
                    ):
                        sub["text"] = answer
                        block["is_error"] = False
                        return result
    return result


def _format_multi_answer(prompt: str, questions: list[Any] | None) -> str:
    """把用户的多问题答案解析并格式化为 header: value 行

    支持 JSON 格式：{"header1": "value1", "header2": "value2"}
    multiSelect 用数组：{"header": ["v1", "v2"]}

    格式化逻辑与 ask_user_question 工具的 dict 返回一致：
    - str 值 → "header: value"
    - list 值 → 每个元素一行 "header: item"

    单问题或解析失败时原样返回 prompt（向后兼容）。

    Args:
        prompt: 用户输入的答案文本
        questions: 持久化的问题列表（含 header 字段）

    Returns:
        str: 格式化后的答案字符串
    """
    if not questions or len(questions) <= 1:
        return prompt
    import json as _json
    text = prompt.strip()
    if not text.startswith("{"):
        return prompt  # 非 JSON，原样返回
    try:
        answers = _json.loads(text)
    except (ValueError, TypeError):
        return prompt  # 解析失败，原样返回
    if not isinstance(answers, dict):
        return prompt
    # 格式化为 header: value 行（与 ask_user_question 工具的 dict 格式化逻辑一致）
    lines: list[str] = []
    for k, v in answers.items():
        if isinstance(v, list):
            for item in v:
                lines.append(f"{k}: {item}")
        else:
            lines.append(f"{k}: {v}")
    return "\n".join(lines) if lines else prompt


def _parse_plan_approval(prompt: str) -> dict[str, Any]:
    """解析用户对计划审批的回复

    支持的输入：
        - "批准" / "approve" / "yes" / "y" (case-insensitive) → 批准
        - 其他任何输入 → 视为拒绝，输入原文作为反馈

    Args:
        prompt: 用户输入的审批回复

    Returns:
        dict: {"approved": bool, "feedback": str}
    """
    text = prompt.strip().lower()
    approve_keywords = ("批准", "approve", "yes", "y")
    if text in approve_keywords:
        return {"approved": True, "feedback": ""}
    return {"approved": False, "feedback": prompt.strip() or "User rejected the plan."}


def _inject_plan_approval_to_tool_result(
    messages: list[dict[str, Any]],
    approval: dict[str, Any],
) -> list[dict[str, Any]]:
    """把审批结果注入到消息历史中 PENDING_PLAN_APPROVAL_MARKER 的 tool_result

    扫描 messages（反向），找到最后一个 content 包含 PENDING_PLAN_APPROVAL_MARKER
    的 tool_result block，替换为审批结果文本。

    Args:
        messages: 序列化的会话消息列表
        approval: 审批结果 {"approved": bool, "feedback": str}

    Returns:
        list[dict]: 修改后的消息列表（深拷贝）
    """
    import copy
    result = copy.deepcopy(messages)
    if approval["approved"]:
        replacement = "Plan approved. Starting implementation."
    else:
        replacement = f"Plan rejected. Feedback: {approval['feedback']}"
    # 反向扫描，找最后一个 PENDING_PLAN_APPROVAL_MARKER 的 tool_result
    for msg in reversed(result):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue
            block_content = block.get("content")
            if isinstance(block_content, str) and PENDING_PLAN_APPROVAL_MARKER in block_content:
                block["content"] = replacement
                block["is_error"] = not approval["approved"]
                return result
            if isinstance(block_content, list):
                for sub in block_content:
                    if (
                        isinstance(sub, dict)
                        and isinstance(sub.get("text"), str)
                        and PENDING_PLAN_APPROVAL_MARKER in sub["text"]
                    ):
                        sub["text"] = replacement
                        block["is_error"] = not approval["approved"]
                        return result
    return result


def _parse_permission_response(prompt: str) -> dict[str, Any]:
    """解析用户权限审批输入

    支持的输入（不区分大小写）：
    - "y"/"yes"/"批准" → allow（一次性允许）
    - "f"/"always"/"始终" → always_allow（永久允许）
    - 其他 → deny（拒绝）

    Args:
        prompt: 用户输入文本

    Returns:
        dict: {"decision": "allow"|"always_allow"|"deny"}
    """
    text = prompt.strip().lower()
    if text in ("y", "yes", "批准"):
        return {"decision": "allow"}
    if text in ("f", "always", "始终"):
        return {"decision": "always_allow"}
    return {"decision": "deny"}


def _inject_permission_to_tool_result(
    messages: list[dict[str, Any]],
    tool_name: str,
    decision: str,
) -> list[dict[str, Any]]:
    """把权限审批结果注入到消息历史中的合成 tool_result

    反向扫描 messages，找到包含 "Permission denied for {tool_name}" 的
    error tool_result，替换为审批结果文本。

    Args:
        messages: 消息历史列表
        tool_name: 被请求权限的工具名称
        decision: 审批决策 ("allow"|"always_allow"|"deny")

    Returns:
        list: 修改后的消息历史
    """
    if decision == "allow":
        new_content = "Permission approved by user. Please retry the tool call."
    elif decision == "always_allow":
        new_content = "Permission approved (always) by user. Please retry the tool call."
    else:
        new_content = "Permission denied by user."
    target = f"Permission denied for {tool_name}"
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    block_content = block.get("content", "")
                    if isinstance(block_content, str) and target in block_content:
                        block["content"] = new_content
                        block["is_error"] = decision == "deny"
                        return messages
        elif isinstance(content, str) and target in content:
            msg["content"] = new_content
            return messages
    return messages


async def run_repl(
    *,
    prompt: str | None = None,
    cwd: str | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    api_client: SupportsStreamingMessages | None = None,
    backend_only: bool = False,
    restore_messages: list[dict[str, Any]] | None = None,
    restore_session_id: str | None = None,
    effort: str | None = None,
    channel_hint: str | None = None,
    channel_tools: list[Any] | None = None,
    permission_mode: str | None = None,
    name: str | None = None,
    continue_session: bool = False,
    resume: str | None = None,
) -> None:
    """运行默认的 IllusionAgent 交互式应用程序（React TUI）。

    Args:
        prompt: 初始提示词
        cwd: 工作目录
        model: 使用的模型名称
        max_turns: 最大对话轮次
        api_client: 流式 API 客户端实例
        backend_only: 是否仅运行后端
        restore_messages: 恢复的会话消息列表
        restore_session_id: 恢复的会话ID
        effort: 推理强度级别（low/medium/high/xhigh/max）
        channel_hint: 渠道感知提示词（PC 终端注入系统提示词，含已启用渠道概览）
        channel_tools: 跨渠道工具列表（如 SendToChannelTool）
        permission_mode: 权限模式
        name: 会话名称
        continue_session: 继续上一会话
        resume: 恢复指定会话
    """
    # 后端单独运行模式
    if backend_only:
        await run_backend_host(
            cwd=cwd,
            model=model,
            max_turns=max_turns,
            api_client=api_client,
            restore_messages=restore_messages,
            restore_session_id=restore_session_id,
            enforce_max_turns=max_turns is not None,
            effort=effort,
            channel_hint=channel_hint,
            channel_tools=channel_tools,
            permission_mode=permission_mode,
            name=name,
            continue_session=continue_session,
            resume=resume,
        )
        return

    # 启动 React TUI 前端
    exit_code = await launch_react_tui(
        prompt=prompt,
        cwd=cwd,
        model=model,
        max_turns=max_turns,
        effort=effort,
        permission_mode=permission_mode,
        name=name,
        continue_session=continue_session,
        resume=resume,
    )
    # 如果前端退出代码非零，抛出 SystemExit
    if exit_code != 0:
        raise SystemExit(exit_code)


async def run_print_mode(
    *,
    prompt: str,
    output_format: str = "text",
    cwd: str | None = None,
    model: str | None = None,
    api_client: SupportsStreamingMessages | None = None,
    permission_mode: str | None = None,
    max_turns: int | None = None,
    effort: str | None = None,
    continue_session: bool = False,
    resume: str | None = None,
    name: str | None = None,
) -> None:
    """非交互式模式：提交提示词，流式输出，然后退出。

    Args:
        prompt: 用户提示词
        output_format: 输出格式（text/json/stream-json）
        cwd: 工作目录
        model: 使用的模型名称
        api_client: 流式 API 客户端实例
        permission_mode: 权限模式
        max_turns: 最大对话轮次
        effort: 推理强度级别
        continue_session: 继续上一会话
        resume: 恢复指定会话 ID（空字符串则报错）
        name: 会话名称
    """
    import time
    from pathlib import Path

    from illusion.config.i18n import t as _t
    from illusion.engine.stream_events import (
        AssistantTextDelta,
        AssistantTurnComplete,
        ErrorEvent,
        StatusEvent,
        ToolExecutionCompleted,
        ToolExecutionStarted,
    )
    from illusion.services.session_storage import (
        delete_pending_permission,
        delete_pending_plan_approval,
        delete_pending_question,
        get_project_session_dir_no_create,
        load_pending_permission,
        load_pending_plan_approval,
        load_pending_question,
        read_index,
        read_meta,
    )
    from illusion.ui.permission_store import add_always_allowed_tool
    from illusion.ui.terminal_io import (
        PENDING_ANSWER_MARKER,
        PENDING_PLAN_APPROVAL_MARKER,
        make_print_mode_ask_user,
        make_print_mode_permission,
        make_print_mode_plan_approval,
    )

    # 会话恢复
    restore_messages: list[dict[str, Any]] | None = None
    restore_session_id: str | None = None
    effective_cwd = cwd or str(Path.cwd())
    from illusion.services.checkpoint_store import CheckpointStore
    if continue_session:
        index = read_index(effective_cwd)
        if index is None or not index.get("latest_session_id"):
            print(_t("session_not_found_prev"), file=sys.stderr)
            raise SystemExit(1)
        sid = index["latest_session_id"]
        meta = read_meta(effective_cwd, sid) or {}
        session_dir = get_project_session_dir_no_create(effective_cwd) / sid
        if not session_dir.exists():
            print(_t("session_not_found_prev"), file=sys.stderr)
            raise SystemExit(1)
        store = CheckpointStore(session_dir, sid)
        restore_result = await store.restore()
        restore_messages = [m.model_dump(mode="json") for m in restore_result.messages]
        restore_session_id = sid
        print(_t("session_continuing", summary=meta.get('summary') or _t("session_summary_fallback")))
    elif resume is not None:
        if resume == "":
            print(_t("session_resume_requires_id"), file=sys.stderr)
            raise SystemExit(1)
        meta = read_meta(effective_cwd, resume) or {}
        if not meta:
            print(_t("session_not_found_id", session_id=resume), file=sys.stderr)
            raise SystemExit(1)
        session_dir = get_project_session_dir_no_create(effective_cwd) / resume
        store = CheckpointStore(session_dir, resume)
        restore_result = await store.restore()
        restore_messages = [m.model_dump(mode="json") for m in restore_result.messages]
        restore_session_id = resume
        print(_t("session_continuing", summary=meta.get('summary') or _t("session_summary_fallback")))

    # 检测 pending question（上次 print 模式退出时遗留的待回答问题）
    pending_question: dict[str, Any] | None = None
    if restore_session_id:
        pending_question = load_pending_question(effective_cwd, restore_session_id)
        if pending_question:
            # 把用户的 prompt 作为答案注入到消息历史中的 PENDING_ANSWER_MARKER tool_result
            if restore_messages:
                # 多问题时，把 JSON 格式答案解析为 header: value 行（与工具 dict 返回一致）
                questions_data = pending_question.get("questions") or []
                formatted_answer = _format_multi_answer(prompt, questions_data)
                restore_messages = _inject_answer_to_pending_tool_result(
                    restore_messages, formatted_answer
                )
            delete_pending_question(effective_cwd, restore_session_id)
            print(_t("print_mode_resuming_answer"), file=sys.stderr)

    # 检测 pending plan approval（上次 print 模式退出时遗留的待审批计划）
    pending_plan_approval: dict[str, Any] | None = None
    if restore_session_id:
        pending_plan_approval = load_pending_plan_approval(effective_cwd, restore_session_id)
        if pending_plan_approval:
            # 将用户输入解析为审批结果，注入到 exit_plan_mode 的 tool_result
            approval_result = _parse_plan_approval(prompt)
            if restore_messages:
                restore_messages = _inject_plan_approval_to_tool_result(
                    restore_messages, approval_result
                )
            delete_pending_plan_approval(effective_cwd, restore_session_id)
            if approval_result["approved"]:
                print(_t("print_mode_plan_approved"), file=sys.stderr)
            else:
                print(_t("print_mode_plan_rejected"), file=sys.stderr)
            print(_t("print_mode_plan_resuming_approval"), file=sys.stderr)

    # 检测 pending permission（上次 print 模式退出时遗留的待审批权限）
    pending_permission: dict[str, Any] | None = None
    if restore_session_id:
        pending_permission = load_pending_permission(effective_cwd, restore_session_id)
        if pending_permission:
            # 将用户输入解析为权限决策
            perm_decision = _parse_permission_response(prompt)
            tool_name = pending_permission.get("tool_name", "")
            if perm_decision["decision"] == "allow":
                # Y：更新 pending 文件 approved=true，callback 读取后放行并删除
                # 直接原子写覆盖（approved=true）
                import json as _json

                from illusion.utils.atomic_write import atomic_write_text
                _perm_payload = {
                    "session_id": restore_session_id,
                    "tool_name": tool_name,
                    "reason": pending_permission.get("reason", ""),
                    "approved": True,
                    "created_at": pending_permission.get("created_at", time.time()),
                }
                from illusion.services.session_storage import _pending_permission_path
                _perm_path = _pending_permission_path(effective_cwd, restore_session_id)
                atomic_write_text(_perm_path, _json.dumps(_perm_payload, indent=2, ensure_ascii=False) + "\n")
                print(_t("print_mode_permission_approved"), file=sys.stderr)
            elif perm_decision["decision"] == "always_allow":
                # F：添加到 always_allow_tools，删除 pending 文件
                add_always_allowed_tool(effective_cwd, tool_name)
                delete_pending_permission(effective_cwd, restore_session_id)
                print(_t("print_mode_permission_always_approved"), file=sys.stderr)
            else:
                # N：删除 pending 文件
                delete_pending_permission(effective_cwd, restore_session_id)
                print(_t("print_mode_permission_denied_resuming"), file=sys.stderr)
            # 修改消息历史中的合成 tool_result
            if restore_messages:
                restore_messages = _inject_permission_to_tool_result(
                    restore_messages, tool_name, perm_decision["decision"]
                )
            print(_t("print_mode_permission_resuming"), file=sys.stderr)

    # 预生成 session_id（确保 make_print_mode_ask_user 和 build_runtime 一致）
    from uuid import uuid4
    effective_session_id = restore_session_id or uuid4().hex[:12]

    # 构造 print 模式非交互状态字典
    print_state: dict[str, Any] = {}

    # 构建运行时
    bundle = await build_runtime(
        prompt=prompt,
        model=model,
        max_turns=max_turns,
        api_client=api_client,
        permission_prompt=make_print_mode_permission(
            cwd=effective_cwd,
            session_id=effective_session_id,
            state=print_state,
        ),
        ask_user_prompt=make_print_mode_ask_user(
            cwd=effective_cwd,
            session_id=effective_session_id,
            state=print_state,
        ),
        plan_approval_prompt=make_print_mode_plan_approval(
            cwd=effective_cwd,
            session_id=effective_session_id,
            state=print_state,
        ),
        effort=effort,
        permission_mode=permission_mode,
        name=name,
        restore_messages=restore_messages,
        restore_session_id=effective_session_id,
    )
    await start_runtime(bundle)

    # 收集输出
    collected_text = ""
    events_list: list[dict[str, Any]] = []
    # 前缀打印状态：跟踪当前段是否已输出前缀（避免每个 delta 重复输出）
    # 工具事件后重置，使下一轮思考/回复获得新前缀
    _reasoning_prefix_printed = False
    _assistant_prefix_printed = False
    # 是否已输出过至少一个段落（用于在段落间插入空行分隔）
    _any_section_printed = False

    try:
        # 系统消息打印回调
        async def _print_system(message: str) -> None:
            nonlocal collected_text
            if output_format == "text":
                print(message, file=sys.stderr)
            elif output_format == "stream-json":
                obj = {"type": "system", "message": message}
                print(json.dumps(obj), flush=True)
                events_list.append(obj)

        def _print_section_header(header: str) -> None:
            """输出段落前缀，非首个段落前加空行分隔

            若上一段内容未以换行结尾（如 reasoning 通过 write 输出），
            先补一个换行再输出空行，确保段落视觉分隔清晰。
            """
            nonlocal _any_section_printed
            if _any_section_printed:
                print(file=sys.stderr)  # 空行分隔
            print(header, file=sys.stderr)
            _any_section_printed = True

        # 流式事件渲染回调
        async def _render_event(event: StreamEvent) -> None:
            nonlocal collected_text, _reasoning_prefix_printed, _assistant_prefix_printed, _any_section_printed
            obj: dict[str, Any]
            # 助手文本/思考增量（同一事件可能携带 text 和/或 reasoning）
            if isinstance(event, AssistantTextDelta):
                # 思考过程：输出到 stderr（text 模式），stream-json 加入 reasoning 字段
                if event.reasoning:
                    if output_format == "text":
                        if not _reasoning_prefix_printed:
                            _print_section_header(_t("print_mode_prefix_reasoning"))
                            _reasoning_prefix_printed = True
                        sys.stderr.write(event.reasoning)
                        sys.stderr.flush()
                    elif output_format == "stream-json":
                        obj = {"type": "assistant_delta", "text": "", "reasoning": event.reasoning}
                        print(json.dumps(obj), flush=True)
                        events_list.append(obj)
                # 最终回复：stdout 保持清洁，前缀标记输出到 stderr
                if event.text:
                    collected_text += event.text
                    if output_format == "text":
                        if not _assistant_prefix_printed:
                            # 思考段后补换行，使下一前缀从新行开始
                            if _reasoning_prefix_printed:
                                sys.stderr.write("\n")
                                sys.stderr.flush()
                            _print_section_header(_t("print_mode_prefix_assistant"))
                            _assistant_prefix_printed = True
                        sys.stdout.write(event.text)
                        sys.stdout.flush()
                    elif output_format == "stream-json":
                        obj = {"type": "assistant_delta", "text": event.text}
                        print(json.dumps(obj), flush=True)
                        events_list.append(obj)
            # 助手回合完成
            elif isinstance(event, AssistantTurnComplete):
                # 重置前缀标记，为下一轮做准备
                _reasoning_prefix_printed = False
                _assistant_prefix_printed = False
                if output_format == "text":
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                elif output_format == "stream-json":
                    obj = {"type": "assistant_complete", "text": event.message.text.strip()}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)
            # 工具开始执行
            elif isinstance(event, ToolExecutionStarted):
                # 重置前缀标记：工具调用后下一轮思考/回复需要新前缀
                _reasoning_prefix_printed = False
                _assistant_prefix_printed = False
                if output_format == "text":
                    _print_section_header(_t("print_mode_prefix_tool_call") + " " + event.tool_name)
                elif output_format == "stream-json":
                    obj = {"type": "tool_started", "tool_name": event.tool_name, "tool_input": event.tool_input}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)
            # 工具执行完成
            elif isinstance(event, ToolExecutionCompleted):
                if output_format == "text":
                    marker = "❌" if event.is_error else "✅"
                    # 检测 pending marker，替换为友好提示
                    output = event.output
                    if output == PENDING_ANSWER_MARKER:
                        output = _t("print_mode_pending_answer_hint")
                    elif output == PENDING_PLAN_APPROVAL_MARKER:
                        output = _t("print_mode_pending_plan_hint")
                    _print_section_header(f"{_t('print_mode_prefix_tool_result')} {marker} {event.tool_name}")
                    # 完整输出工具结果（print 模式面向 agent，不截断）
                    print(output, file=sys.stderr)
                elif output_format == "stream-json":
                    obj = {"type": "tool_completed", "tool_name": event.tool_name, "output": event.output, "is_error": event.is_error}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)
            # 错误事件
            elif isinstance(event, ErrorEvent):
                if output_format == "text":
                    print(event.message, file=sys.stderr)
                elif output_format == "stream-json":
                    obj = {"type": "error", "message": event.message, "recoverable": event.recoverable}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)
            # 状态事件
            elif isinstance(event, StatusEvent):
                if output_format == "text":
                    print(event.message, file=sys.stderr)
                elif output_format == "stream-json":
                    obj = {"type": "status", "message": event.message}
                    print(json.dumps(obj), flush=True)
                    events_list.append(obj)

        # 空清空输出回调
        async def _clear_output() -> None:
            pass

        # 执行：如果有 pending_question，用 continue_pending（答案已注入 messages）
        # 否则用 handle_line 正常提交新 prompt
        if pending_question:
            # 答案已注入到 restore_messages 中，直接继续执行
            from illusion.engine.query import MaxTurnsExceeded
            try:
                async for event in bundle.engine.continue_pending(
                    max_turns=bundle.engine.max_turns
                ):
                    await _render_event(event)
            except MaxTurnsExceeded as exc:
                await _print_system(_t("print_mode_max_turns_stopped", max_turns=exc.max_turns))
        else:
            await handle_line(
                bundle,
                prompt,
                print_system=_print_system,
                render_event=_render_event,
                clear_output=_clear_output,
            )

        # JSON 格式输出最终结果
        if output_format == "json":
            result = {"type": "result", "text": collected_text.strip()}
            print(json.dumps(result))

        # 如果 ask_user_question 或 exit_plan_mode 触发了 pending 状态，以退出码 2 退出
        if (
            print_state.get("pending_question_raised")
            or print_state.get("pending_plan_approval_raised")
            or print_state.get("pending_permission_raised")
        ):
            # 打印 pending 状态指引（含文件路径和审批命令）
            if print_state.get("pending_question_raised"):
                print(_t("print_mode_pending_question_exit"), file=sys.stderr)
            if print_state.get("pending_plan_approval_raised"):
                plan_path = print_state.get("pending_plan_path", "")
                print(_t("print_mode_pending_plan_exit", path=plan_path), file=sys.stderr)
            if print_state.get("pending_permission_raised"):
                tool_name = print_state.get("pending_permission_tool", "")
                print(_t("print_mode_pending_permission_exit", tool=tool_name), file=sys.stderr)
            raise SystemExit(2)
    finally:
        # 关闭运行时
        await close_runtime(bundle)