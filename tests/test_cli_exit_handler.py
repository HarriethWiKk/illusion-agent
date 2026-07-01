"""cli.py 退出处理器调用测试

验证 main() 和 web_start() 的 finally 块调用 handle_daemon_exit_on_interrupt，
而非内联的 _kill_channel_daemon 闭包。
"""
from __future__ import annotations

import inspect


def test_cli_imports_handle_daemon_exit_on_interrupt():
    """cli.py 应导入 handle_daemon_exit_on_interrupt"""
    import illusion.cli as cli_module
    # 验证 cli 模块不再定义 _kill_channel_daemon 闭包（在 main 函数内部）
    source = inspect.getsource(cli_module.main)
    assert "_kill_channel_daemon" not in source, "main() 不应再包含 _kill_channel_daemon 闭包"
    assert "handle_daemon_exit_on_interrupt" in source, "main() 应调用 handle_daemon_exit_on_interrupt"


def test_web_start_calls_handle_daemon_exit_on_interrupt():
    """web_start() 应调用 handle_daemon_exit_on_interrupt"""
    import illusion.cli as cli_module
    source = inspect.getsource(cli_module.web_start)
    assert "handle_daemon_exit_on_interrupt" in source, "web_start() 应调用 handle_daemon_exit_on_interrupt"


def test_i18n_exit_prompt_uses_Y_n():
    """channel_daemon_exit_prompt 文案应为 (Y/n) 而非 (y/N)"""
    from illusion.config.i18n import MESSAGES
    prompt = MESSAGES["channel_daemon_exit_prompt"]
    assert "(Y/n)" in prompt["zh-CN"]
    assert "(Y/n)" in prompt["en-US"]
