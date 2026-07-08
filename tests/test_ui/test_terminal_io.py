"""terminal_io 终端交互回调测试。"""
from __future__ import annotations

import pytest

from illusion.ui.terminal_io import format_question_options


def test_format_question_options_multi_server():
    """多问题多选项格式化。"""
    questions = [
        {
            "question": "选择模型",
            "header": "Model",
            "options": [
                {"label": "sonnet", "description": "快速"},
                {"label": "opus", "description": "强力"},
            ],
            "multiSelect": False,
        }
    ]
    result = format_question_options(questions)
    assert "【Model】" in result
    assert "选择模型" in result
    assert "• sonnet — 快速" in result
    assert "• opus — 强力" in result


def test_format_question_options_empty():
    """空输入返回空字符串。"""
    assert format_question_options(None) == ""
    assert format_question_options([]) == ""
    assert format_question_options([{}]) == ""


def test_format_question_options_no_desc():
    """选项无描述时不附加 — 后缀。"""
    questions = [
        {
            "header": "Test",
            "options": [{"label": "yes"}, {"label": "no"}],
        }
    ]
    result = format_question_options(questions)
    assert "• yes" in result
    assert "• no" in result
    assert "—" not in result


@pytest.mark.asyncio
async def test_terminal_permission_eof_returns_false(monkeypatch):
    """EOF 时权限返回 False。"""
    from illusion.ui.terminal_io import terminal_permission

    # 模拟 EOFError
    monkeypatch.setattr("builtins.input", lambda *a: (_ for _ in ()).throw(EOFError()))
    result = await terminal_permission("bash", "test reason")
    assert result is False


@pytest.mark.asyncio
async def test_terminal_permission_y_returns_true(monkeypatch):
    """输入 y 时权限返回 True。"""
    from illusion.ui.terminal_io import terminal_permission

    monkeypatch.setattr("builtins.input", lambda *a: "y")
    result = await terminal_permission("bash", "test reason")
    assert result is True


@pytest.mark.asyncio
async def test_terminal_permission_other_returns_false(monkeypatch):
    """输入非 y 时权限返回 False。"""
    from illusion.ui.terminal_io import terminal_permission

    monkeypatch.setattr("builtins.input", lambda *a: "n")
    result = await terminal_permission("bash", "test reason")
    assert result is False


@pytest.mark.asyncio
async def test_terminal_ask_user_returns_input(monkeypatch):
    """ask_user 返回用户输入。"""
    from illusion.ui.terminal_io import terminal_ask_user

    monkeypatch.setattr("builtins.input", lambda *a: "sonnet")
    result = await terminal_ask_user("选择模型?", None)
    assert result == "sonnet"


@pytest.mark.asyncio
async def test_terminal_ask_user_eof_returns_empty(monkeypatch):
    """EOF 时 ask_user 返回空字符串。"""
    from illusion.ui.terminal_io import terminal_ask_user

    monkeypatch.setattr("builtins.input", lambda *a: (_ for _ in ()).throw(EOFError()))
    result = await terminal_ask_user("选择?", None)
    assert result == ""
