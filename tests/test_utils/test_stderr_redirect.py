"""StderrRedirector 单元测试。"""

from __future__ import annotations

import logging
import os

from illusion.utils.stderr_redirect import StderrRedirector


def test_install_uninstall_roundtrip():
    """install 后 stderr 被重定向，uninstall 后恢复。"""
    redirector = StderrRedirector(logger_name="test_stderr", level=logging.ERROR)
    redirector.install()
    try:
        # install 后写 stderr 应该不直接输出到原 stderr
        os.write(2, b"redirected line\n")
    finally:
        redirector.uninstall()


def test_uninstall_is_idempotent():
    """uninstall 可重复调用不报错。"""
    redirector = StderrRedirector(logger_name="test_stderr")
    redirector.install()
    redirector.uninstall()
    redirector.uninstall()  # 幂等


def test_install_is_idempotent():
    """install 可重复调用不报错。"""
    redirector = StderrRedirector(logger_name="test_stderr")
    redirector.install()
    redirector.install()  # 幂等
    redirector.uninstall()


def test_open_original_stderr_handle():
    """install 后仍可获取原始 stderr 句柄。"""
    redirector = StderrRedirector(logger_name="test_stderr")
    redirector.install()
    try:
        handle = redirector.open_original_stderr_handle()
        assert handle is not None
        handle.close()
    finally:
        redirector.uninstall()
