"""print 模式增强测试：终端交互回调 + 会话恢复。"""
from __future__ import annotations

import pytest

from illusion.api.client import ApiMessageCompleteEvent
from illusion.api.usage import UsageSnapshot
from illusion.engine.messages import ConversationMessage, TextBlock


class StaticApiClient:
    """Fake streaming client for print mode tests."""

    async def stream_message(self, request):
        del request
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="ok")]),
            usage=UsageSnapshot(input_tokens=2, output_tokens=3),
            stop_reason=None,
        )


@pytest.mark.asyncio
async def test_print_mode_uses_terminal_callbacks(tmp_path, monkeypatch):
    """print 模式应使用 print_mode_permission/make_print_mode_ask_user（非交互回调）。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ILLUSION_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))

    from illusion.ui.app import run_print_mode

    # 不应崩溃——终端回调在 EOF 时安全返回
    await run_print_mode(
        prompt="hello",
        cwd=str(tmp_path),
        api_client=StaticApiClient(),
        output_format="text",
    )


@pytest.mark.asyncio
async def test_print_mode_continue_without_session_fails(tmp_path, monkeypatch):
    """continue_session=True 但无历史会话时应报错退出。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ILLUSION_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))

    from illusion.ui.app import run_print_mode

    with pytest.raises(SystemExit):
        await run_print_mode(
            prompt="continue",
            cwd=str(tmp_path),
            api_client=StaticApiClient(),
            continue_session=True,
        )


@pytest.mark.asyncio
async def test_print_mode_resume_empty_string_fails(tmp_path, monkeypatch):
    """resume='' 在 print 模式下应报错（不打开选择器）。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ILLUSION_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ILLUSION_DATA_DIR", str(tmp_path / "data"))

    from illusion.ui.app import run_print_mode

    with pytest.raises(SystemExit):
        await run_print_mode(
            prompt="resume",
            cwd=str(tmp_path),
            api_client=StaticApiClient(),
            resume="",
        )
