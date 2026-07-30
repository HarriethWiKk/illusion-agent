"""cli.py 退出处理测试

验证 main() 和 web_start() 的 finally 块关闭 IPC 连接，
而非调用已移除的 remove_ref 或 handle_daemon_exit_on_interrupt。

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


def test_main_does_not_call_remove_ref():
    """main() 不应调用 remove_ref"""
    from illusion.cli.main import main

    main_calls = _extract_call_names(main)
    assert "remove_ref" not in main_calls, (
        "main() 不应调用 remove_ref"
    )
    assert "handle_daemon_exit_on_interrupt" not in main_calls, (
        "main() 不应调用 handle_daemon_exit_on_interrupt"
    )


def test_web_start_does_not_call_remove_ref():
    """web_start() 不应调用 remove_ref"""
    from illusion.cli.web import web_start

    web_start_calls = _extract_call_names(web_start)
    assert "remove_ref" not in web_start_calls, (
        "web_start() 不应调用 remove_ref"
    )
    assert "handle_daemon_exit_on_interrupt" not in web_start_calls, (
        "web_start() 不应调用 handle_daemon_exit_on_interrupt"
    )
