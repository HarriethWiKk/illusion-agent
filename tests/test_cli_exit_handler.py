"""cli.py 退出处理器调用测试

验证 main() 和 web_start() 的 finally 块调用 handle_daemon_exit_on_interrupt，
而非内联的 _kill_channel_daemon 闭包。

使用 ast 解析验证真正的函数调用，而非源码字符串匹配（避免注释误判）。
"""
from __future__ import annotations

import ast
import inspect


def _extract_call_names(func) -> set[str]:
    """从函数源码 AST 中提取所有被调用的函数名

    Args:
        func: 待分析的函数对象

    Returns:
        set[str]: 所有被调用的函数名集合（仅 Name 调用，不含属性调用）
    """
    source = inspect.getsource(func)
    # 缩进修复：getsource 返回的源码可能有缩进，需 dedent 后才能 parse
    tree = ast.parse(inspect.cleandoc(source))
    call_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            call_names.add(node.func.id)
    return call_names


def test_cli_imports_handle_daemon_exit_on_interrupt():
    """cli.py 应在 main() 内导入并调用 handle_daemon_exit_on_interrupt

    注意：cli.py 使用函数内局部导入（from ... import），不是模块级导入，
    所以不能用 hasattr 验证。改用 AST 验证 ImportFrom + Call 节点。
    """
    import illusion.cli as cli_module

    # 用 AST 验证 main() 真正调用了该函数（注释/字符串不会误判为调用）
    main_calls = _extract_call_names(cli_module.main)
    assert "handle_daemon_exit_on_interrupt" in main_calls, (
        "main() 应调用 handle_daemon_exit_on_interrupt"
    )
    assert "_kill_channel_daemon" not in main_calls, (
        "main() 不应再调用 _kill_channel_daemon 闭包"
    )


def test_web_start_calls_handle_daemon_exit_on_interrupt():
    """web_start() 应调用 handle_daemon_exit_on_interrupt"""
    import illusion.cli as cli_module

    web_start_calls = _extract_call_names(cli_module.web_start)
    assert "handle_daemon_exit_on_interrupt" in web_start_calls, (
        "web_start() 应调用 handle_daemon_exit_on_interrupt"
    )


def test_i18n_exit_prompt_uses_Y_n():
    """channel_daemon_exit_prompt 文案应为 (Y/n) 而非 (y/N)"""
    from illusion.config.i18n import MESSAGES
    prompt = MESSAGES["channel_daemon_exit_prompt"]
    assert "(Y/n)" in prompt["zh-CN"]
    assert "(Y/n)" in prompt["en-US"]
