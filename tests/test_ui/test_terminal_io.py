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


@pytest.mark.asyncio
async def test_terminal_permission_yes_full_word_returns_true(monkeypatch):
    """输入完整单词 yes 时权限返回 True（覆盖 yes 分支）。"""
    from illusion.ui.terminal_io import terminal_permission

    monkeypatch.setattr("builtins.input", lambda *a: "yes")
    result = await terminal_permission("bash", "test reason")
    assert result is True


@pytest.mark.asyncio
async def test_terminal_permission_output_contains_i18n_text(monkeypatch, capsys):
    """权限请求输出包含 i18n 文案。"""
    from illusion.ui.terminal_io import terminal_permission

    # 捕获 input 收到的 prompt 参数（input prompt 不走 stdout，需单独捕获）
    captured_prompt: list[str] = []

    def fake_input(prompt: str = "") -> str:
        captured_prompt.append(prompt)
        return "n"

    monkeypatch.setattr("builtins.input", fake_input)
    await terminal_permission("bash", "危险操作")
    captured = capsys.readouterr()
    # 校验 i18n 键对应的文本出现在输出或 input prompt 中
    from illusion.config.i18n import t

    assert t("terminal_permission_request").format(tool_name="bash") in captured.out
    assert t("terminal_permission_reason").format(reason="危险操作") in captured.out
    assert t("terminal_permission_prompt") in captured_prompt


@pytest.mark.asyncio
async def test_terminal_ask_user_with_questions_includes_options(monkeypatch, capsys):
    """ask_user 传入 questions 时输出包含选项文本。"""
    from illusion.ui.terminal_io import terminal_ask_user

    questions = [
        {
            "question": "选择模型",
            "header": "Model",
            "options": [
                {"label": "sonnet", "description": "快速"},
                {"label": "opus", "description": "强力"},
            ],
        }
    ]
    monkeypatch.setattr("builtins.input", lambda *a: "sonnet")
    result = await terminal_ask_user("请选择", questions)
    captured = capsys.readouterr()
    assert result == "sonnet"
    # 校验问题文本与选项文本都出现在输出中
    assert "请选择" in captured.out
    assert "【Model】" in captured.out
    assert "• sonnet — 快速" in captured.out
    assert "• opus — 强力" in captured.out
