"""
终端交互回调模块
================

为 print 模式提供终端文字交互能力：
    - format_question_options: 将结构化选项格式化为终端文本
    - terminal_permission: 终端 Y/N 权限确认（仅用于 TUI 后端）
    - terminal_ask_user: 终端用户问答（仅用于 TUI 后端）
    - make_print_mode_ask_user: print 模式非交互问答回调工厂
    - print_mode_permission: print 模式非交互权限回调（直接拒绝）

参考 channels 的 _format_question_options 实现，提取为共享函数。
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from illusion.config.i18n import t

# print 模式 ask_user_question 返回的特殊标记
# 作为 tool_result 存储在消息历史中，恢复时用于定位待回答的问题
PENDING_ANSWER_MARKER = "__PENDING_ANSWER__"

# print 模式 exit_plan_mode 返回的特殊标记
# 作为 tool_result 存储在消息历史中，恢复时用于定位待审批的计划
PENDING_PLAN_APPROVAL_MARKER = "__PENDING_PLAN_APPROVAL__"

# print 模式权限请求标记（state flag 用，非 tool_result）
PENDING_PERMISSION_MARKER = "__PENDING_PERMISSION__"


def format_question_options(questions: object) -> str:
    """将结构化问题选项格式化为终端可显示的文本

    questions 结构：list[dict]，每个 dict 含：
        - question: str 子问题文本
        - header: str 标题
        - options: list[dict] 选项列表，每项含 label/description
        - multiSelect: bool 是否多选
        - noCustomInput: bool 是否禁止自定义输入

    Args:
        questions: 结构化问题数据

    Returns:
        str: 格式化后的选项文本，无选项返回空串
    """
    if not isinstance(questions, (list, tuple)):
        return ""
    lines: list[str] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        opts = q.get("options") or []
        if not opts:
            continue
        header = str(q.get("header") or "").strip()
        sub_q = str(q.get("question") or "").strip()
        if header:
            lines.append(t("question_header_format").format(header=header))
        if sub_q:
            lines.append(sub_q)
        for opt in opts:
            if not isinstance(opt, dict):
                continue
            label = str(opt.get("label") or "").strip()
            desc = str(opt.get("description") or "").strip()
            if label:
                lines.append(f"  • {label}" + (f" — {desc}" if desc else ""))
    return "\n".join(lines)


async def terminal_permission(tool_name: str, reason: str) -> bool:
    """终端权限确认回调（仅用于 TUI 后端）

    在终端显示 Y/N 提示，用户输入 Y=允许，其他=拒绝。
    EOF（如管道输入）时返回 False，避免卡住。

    警告：此函数调用 input() 是交互式的，不得用于 print 模式。
    print 模式应使用 print_mode_permission。

    Args:
        tool_name: 工具名称
        reason: 权限请求原因

    Returns:
        bool: True=允许，False=拒绝
    """
    print(t("terminal_permission_request").format(tool_name=tool_name))
    print(t("terminal_permission_reason").format(reason=reason))
    try:
        answer = (await asyncio.to_thread(input, t("terminal_permission_prompt"))).strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


async def print_mode_permission(tool_name: str, reason: str) -> bool:
    """print 模式非交互权限回调：直接拒绝

    print 模式不能有任何交互操作。当 default 权限模式下工具需要确认时，
    直接拒绝并输出原因到 stderr。用户如需允许工具执行，应使用
    --permission-mode full_auto。

    Args:
        tool_name: 工具名称
        reason: 权限请求原因

    Returns:
        bool: 始终返回 False（拒绝）
    """
    print(t("print_mode_permission_denied").format(tool_name=tool_name, reason=reason), file=sys.stderr)
    return False


async def terminal_ask_user(question: str, questions: object = None) -> str:
    """终端用户问答回调（仅用于 TUI 后端）

    显示问题和选项，用户输入对应 label=选择该选项，
    其他输入=当作"其他"回传。EOF 返回空字符串。

    警告：此函数调用 input() 是交互式的，不得用于 print 模式。
    print 模式应使用 make_print_mode_ask_user。

    Args:
        question: 问题文本
        questions: 结构化选项数据（可选）

    Returns:
        str: 用户输入文本
    """
    text = t("terminal_ask_user_question").format(question=question)
    if questions:
        opts_text = format_question_options(questions)
        if opts_text:
            text = f"{text}\n\n{opts_text}"
    print(text)
    try:
        answer = (await asyncio.to_thread(input, "> ")).strip()
    except EOFError:
        return ""
    return answer


def make_print_mode_ask_user(
    *,
    cwd: str,
    session_id: str | None,
    state: dict[str, Any],
) -> Any:
    """构造 print 模式非交互 ask_user_question 回调

    回调行为：
        1. 持久化问题到 pending-question 文件
        2. 设置 state["pending_question_raised"] = True
        3. 返回 PENDING_ANSWER_MARKER 作为 tool_result

    agent 收到该标记后会结束当前轮次，run_print_mode 检测到
    state["pending_question_raised"] 后以退出码 2 退出。
    下次 illusion -c -p "答案" 恢复时，答案会注入为 tool_result。

    Args:
        cwd: 工作目录
        session_id: 会话 ID
        state: 共享状态字典（用于通知 run_print_mode）

    Returns:
        ask_user_prompt 回调函数
    """

    async def _ask(question: str, questions: object = None) -> str:
        # 持久化问题
        if session_id:
            from illusion.services.session_storage import save_pending_question
            questions_list = (
                [q if isinstance(q, dict) else _question_item_to_dict(q) for q in questions]
                if isinstance(questions, (list, tuple))
                else []
            )
            save_pending_question(
                cwd=cwd,
                session_id=session_id,
                tool_use_id="",  # 恢复时从消息历史中定位，不需要显式记录
                questions=questions_list,
                question_text=question,
            )
        # 通知 run_print_mode
        state["pending_question_raised"] = True
        # 输出问题到 stderr（text 模式）供调用方查看
        print(t("print_mode_question_asked"), file=sys.stderr)
        print(question, file=sys.stderr)
        if questions:
            opts_text = format_question_options(questions)
            if opts_text:
                print(opts_text, file=sys.stderr)
            # 多问题时，提示 JSON 回答格式
            if isinstance(questions, (list, tuple)) and len(questions) > 1:
                headers = [
                    str(q.get("header", "")) for q in questions
                    if isinstance(q, dict) and q.get("header")
                ]
                if headers:
                    example_pairs = [f'"{h}": "<选择>"' for h in headers]
                    example = "{" + ", ".join(example_pairs) + "}"
                    print(t("print_mode_multi_question_format").format(example=example), file=sys.stderr)
        # 返回特殊标记，作为 tool_result 存储
        return PENDING_ANSWER_MARKER

    return _ask


def _question_item_to_dict(q: Any) -> dict[str, Any]:
    """将 QuestionItem 对象转为 dict（用于持久化）"""
    if hasattr(q, "model_dump"):
        return dict(q.model_dump(mode="json"))
    if isinstance(q, dict):
        return q
    return {"question": str(q)}


def make_print_mode_plan_approval(
    *,
    cwd: str,
    session_id: str | None,
    state: dict[str, Any],
) -> Any:
    """构造 print 模式非交互 plan_approval_prompt 回调

    回调行为：
        1. 持久化计划内容到 pending-plan-approval 文件
        2. 设置 state["pending_plan_approval_raised"] = True
        3. 不输出计划内容到 stderr（agent 自行用 read 工具读计划文件）
        4. 返回 (False, PENDING_PLAN_APPROVAL_MARKER) 让 exit_plan_mode
           返回包含标记的 ToolResult

    agent 收到标记后会结束当前轮次，run_print_mode 检测到
    state["pending_plan_approval_raised"] 后以退出码 2 退出。
    下次 illusion -c -p "批准" 恢复时，审批结果会注入为 tool_result。

    Args:
        cwd: 工作目录
        session_id: 会话 ID
        state: 共享状态字典（用于通知 run_print_mode）

    Returns:
        plan_approval_prompt 回调函数，签名为 async (plan: str) -> tuple[bool, str]
    """
    from illusion.config.plan_file import DEFAULT_SESSION_ID, get_plan_file_path

    async def _approve(plan: str) -> tuple[bool, str]:
        plan_path = str(get_plan_file_path(DEFAULT_SESSION_ID))
        # 持久化计划内容
        if session_id:
            from illusion.services.session_storage import save_pending_plan_approval
            save_pending_plan_approval(
                cwd=cwd,
                session_id=session_id,
                plan=plan,
                plan_path=plan_path,
            )
        # 通知 run_print_mode
        state["pending_plan_path"] = plan_path
        state["pending_plan_approval_raised"] = True
        # 返回 pending 标记，exit_plan_mode 会返回包含标记的 ToolResult
        return (False, PENDING_PLAN_APPROVAL_MARKER)

    return _approve


def make_print_mode_permission(
    *,
    cwd: str,
    session_id: str | None,
    state: dict[str, Any],
) -> Any:
    """print 模式跨轮次权限确认回调工厂

    检查顺序：
    1. always_allow_tools（永久允许，复用现有 .illusion/permissions.json）
    2. pending-permission 文件 approved=true（Y 一次性允许，用完即删）
    3. 未命中：持久化请求 + 设置 state flag + 返回 False

    Args:
        cwd: 工作目录路径
        session_id: 会话 ID（None 时不持久化）
        state: print 模式状态字典（设置 pending_permission_raised flag）

    Returns:
        权限回调函数 (tool_name, reason) -> bool
    """
    from illusion.services.session_storage import (
        delete_pending_permission,
        load_pending_permission,
        save_pending_permission,
    )
    from illusion.ui.permission_store import load_always_allowed_tools
    always_allowed = load_always_allowed_tools(cwd)

    async def _prompt(tool_name: str, reason: str) -> bool:
        # 1. 永久允许
        if tool_name in always_allowed:
            return True
        # 2. 一次性允许（pending 文件 approved=true）
        if session_id:
            pending = load_pending_permission(cwd, session_id)
            if pending and pending.get("tool_name") == tool_name and pending.get("approved"):
                delete_pending_permission(cwd, session_id)  # 一次性，用完即删
                return True
            # 3. 未命中：持久化请求
            save_pending_permission(
                cwd=cwd, session_id=session_id, tool_name=tool_name, reason=reason
            )
        state["pending_permission_tool"] = tool_name
        state["pending_permission_raised"] = True
        return False

    return _prompt
