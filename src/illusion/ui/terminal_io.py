"""
终端交互回调模块
================

为 print 模式提供终端文字交互能力：
    - format_question_options: 将结构化选项格式化为终端文本
    - terminal_permission: 终端 Y/N 权限确认
    - terminal_ask_user: 终端用户问答

参考 channels 的 _format_question_options 实现，提取为共享函数。
"""

from __future__ import annotations


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
            lines.append(f"【{header}】")
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
    """终端权限确认回调

    在终端显示 Y/N 提示，用户输入 Y=允许，其他=拒绝。
    EOF（如管道输入）时返回 False，避免卡住。

    Args:
        tool_name: 工具名称
        reason: 权限请求原因

    Returns:
        bool: True=允许，False=拒绝
    """
    print(f"\n⚠️ 权限请求: {tool_name}")
    print(f"   原因: {reason}")
    try:
        answer = input("   允许执行? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


async def terminal_ask_user(question: str, questions: object = None) -> str:
    """终端用户问答回调

    显示问题和选项，用户输入对应 label=选择该选项，
    其他输入=当作"其他"回传。EOF 返回空字符串。

    Args:
        question: 问题文本
        questions: 结构化选项数据（可选）

    Returns:
        str: 用户输入文本
    """
    text = f"\n❓ {question}"
    if questions:
        opts_text = format_question_options(questions)
        if opts_text:
            text = f"{text}\n\n{opts_text}"
    print(text)
    try:
        answer = input("> ").strip()
    except EOFError:
        return ""
    return answer
