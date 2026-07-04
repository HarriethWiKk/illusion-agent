"""cli.py 退出处理测试

验证 main() 和 web_start() 的 finally 块调用 remove_ref，
而非 handle_daemon_exit_on_interrupt（已废弃）。

使用 ast 解析验证真正的函数调用，而非源码字符串匹配。
"""
from __future__ import annotations

import ast
import inspect


def _extract_call_names(func) -> set[str]:
    """从函数源码 AST 中提取所有被调用的函数名"""
    source = inspect.getsource(func)
    tree = ast.parse(inspect.cleandoc(source))
    call_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            call_names.add(node.func.id)
    return call_names


def test_main_calls_remove_ref():
    """main() 应在 finally 中调用 remove_ref"""
    import illusion.cli as cli_module

    main_calls = _extract_call_names(cli_module.main)
    assert "remove_ref" in main_calls, (
        "main() 应调用 remove_ref 清理引用"
    )
    assert "handle_daemon_exit_on_interrupt" not in main_calls, (
        "main() 不应再调用已废弃的 handle_daemon_exit_on_interrupt"
    )


def test_web_start_calls_remove_ref():
    """web_start() 应调用 remove_ref"""
    import illusion.cli as cli_module

    web_start_calls = _extract_call_names(cli_module.web_start)
    assert "remove_ref" in web_start_calls, (
        "web_start() 应调用 remove_ref 清理引用"
    )
    assert "handle_daemon_exit_on_interrupt" not in web_start_calls, (
        "web_start() 不应再调用已废弃的 handle_daemon_exit_on_interrupt"
    )
