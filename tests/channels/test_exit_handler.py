"""共享退出处理器测试

验证 handle_daemon_exit_on_interrupt 在各种场景下的行为：
- 守护进程未运行 → 直接返回
- channels.json 无配置/无启用渠道 → 直接返回
- 用户确认（y/Y/yes/回车/二次Ctrl+C）→ 停止守护进程
- 用户拒绝（n/任意输入/EOF）→ 不停止守护进程
"""
from __future__ import annotations

import pytest


def _setup_mocks(monkeypatch, *, daemon_running=True, has_enabled=True):
    """配置通用 mock

    Args:
        monkeypatch: pytest monkeypatch
        daemon_running: is_channel_daemon_running 返回值
        has_enabled: has_enabled_channels 返回值

    Returns:
        dict: {"stop_called": bool} 用于追踪 stop_channel_daemon_by_pid 是否被调用
    """
    state = {"stop_called": False}

    def _fake_is_running():
        return daemon_running

    def _fake_stop():
        state["stop_called"] = True
        return True

    def _fake_load_config():
        from unittest.mock import MagicMock
        cfg = MagicMock()
        cfg.has_enabled_channels.return_value = has_enabled
        return cfg

    monkeypatch.setattr(
        "illusion.channels.exit_handler.is_channel_daemon_running", _fake_is_running
    )
    monkeypatch.setattr(
        "illusion.channels.exit_handler.stop_channel_daemon_by_pid", _fake_stop
    )
    monkeypatch.setattr(
        "illusion.channels.exit_handler.load_channels_config", _fake_load_config
    )
    return state


def test_exit_no_daemon_running(monkeypatch):
    """守护进程未运行时直接返回，不调用 stop"""
    state = _setup_mocks(monkeypatch, daemon_running=False, has_enabled=True)

    from illusion.channels.exit_handler import handle_daemon_exit_on_interrupt

    handle_daemon_exit_on_interrupt()
    assert state["stop_called"] is False


def test_exit_no_channels_config(monkeypatch):
    """channels.json 无配置（has_enabled=False）时直接返回"""
    state = _setup_mocks(monkeypatch, daemon_running=True, has_enabled=False)

    from illusion.channels.exit_handler import handle_daemon_exit_on_interrupt

    handle_daemon_exit_on_interrupt()
    assert state["stop_called"] is False


def test_exit_no_enabled_channels(monkeypatch):
    """所有渠道 enabled=false 时直接返回（与 test_exit_no_channels_config 同路径）"""
    state = _setup_mocks(monkeypatch, daemon_running=True, has_enabled=False)

    from illusion.channels.exit_handler import handle_daemon_exit_on_interrupt

    handle_daemon_exit_on_interrupt()
    assert state["stop_called"] is False


def _setup_input(monkeypatch, input_side_effect):
    """配置 input mock"""
    monkeypatch.setattr("builtins.input", input_side_effect)


def test_exit_confirm_with_y(monkeypatch):
    """输入 y 时停止守护进程"""
    state = _setup_mocks(monkeypatch, daemon_running=True, has_enabled=True)
    _setup_input(monkeypatch, lambda *a: "y")

    from illusion.channels.exit_handler import handle_daemon_exit_on_interrupt

    handle_daemon_exit_on_interrupt()
    assert state["stop_called"] is True


def test_exit_confirm_with_Y(monkeypatch):
    """输入 Y 时停止守护进程（大小写不敏感）"""
    state = _setup_mocks(monkeypatch, daemon_running=True, has_enabled=True)
    _setup_input(monkeypatch, lambda *a: "Y")

    from illusion.channels.exit_handler import handle_daemon_exit_on_interrupt

    handle_daemon_exit_on_interrupt()
    assert state["stop_called"] is True


def test_exit_confirm_with_yes(monkeypatch):
    """输入 yes 时停止守护进程"""
    state = _setup_mocks(monkeypatch, daemon_running=True, has_enabled=True)
    _setup_input(monkeypatch, lambda *a: "yes")

    from illusion.channels.exit_handler import handle_daemon_exit_on_interrupt

    handle_daemon_exit_on_interrupt()
    assert state["stop_called"] is True


def test_exit_confirm_with_enter(monkeypatch):
    """输入空字符串（回车）时停止守护进程"""
    state = _setup_mocks(monkeypatch, daemon_running=True, has_enabled=True)
    _setup_input(monkeypatch, lambda *a: "")

    from illusion.channels.exit_handler import handle_daemon_exit_on_interrupt

    handle_daemon_exit_on_interrupt()
    assert state["stop_called"] is True


def test_exit_confirm_with_second_ctrl_c(monkeypatch):
    """input() 抛 KeyboardInterrupt 时停止守护进程（二次 Ctrl+C = 确认）"""
    state = _setup_mocks(monkeypatch, daemon_running=True, has_enabled=True)

    def _raise_keyboard_interrupt(*a):
        raise KeyboardInterrupt()

    _setup_input(monkeypatch, _raise_keyboard_interrupt)

    from illusion.channels.exit_handler import handle_daemon_exit_on_interrupt

    handle_daemon_exit_on_interrupt()
    assert state["stop_called"] is True


def test_exit_reject_with_n(monkeypatch):
    """输入 n 时不停止守护进程"""
    state = _setup_mocks(monkeypatch, daemon_running=True, has_enabled=True)
    _setup_input(monkeypatch, lambda *a: "n")

    from illusion.channels.exit_handler import handle_daemon_exit_on_interrupt

    handle_daemon_exit_on_interrupt()
    assert state["stop_called"] is False


def test_exit_reject_with_arbitrary(monkeypatch):
    """输入任意非确认字符串时不停止守护进程"""
    state = _setup_mocks(monkeypatch, daemon_running=True, has_enabled=True)
    _setup_input(monkeypatch, lambda *a: "xyz123")

    from illusion.channels.exit_handler import handle_daemon_exit_on_interrupt

    handle_daemon_exit_on_interrupt()
    assert state["stop_called"] is False


def test_exit_eof_in_non_tty(monkeypatch):
    """input() 抛 EOFError 时不停止守护进程（非 TTY 环境）"""
    state = _setup_mocks(monkeypatch, daemon_running=True, has_enabled=True)

    def _raise_eof(*a):
        raise EOFError()

    _setup_input(monkeypatch, _raise_eof)

    from illusion.channels.exit_handler import handle_daemon_exit_on_interrupt

    handle_daemon_exit_on_interrupt()
    assert state["stop_called"] is False
