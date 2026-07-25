"""
stderr 重定向模块
=================

本模块提供 fd 级 stderr 重定向，将 C 扩展和 Python warnings 直接写 fd 2 的
输出捕获到 logger，避免污染 TUI 渲染。

主要功能：
    - StderrRedirector: 通过 os.dup2 劫持 fd 2，daemon 线程逐行读取并交给 logger

类说明：
    - StderrRedirector: stderr 重定向器，支持 install/uninstall 生命周期
"""

from __future__ import annotations

import codecs
import contextlib
import locale
import logging
import os
import sys
import threading
from typing import IO


class StderrRedirector:
    """stderr fd 级重定向器。

    通过 os.dup2 将 fd 2 重定向到管道写端，daemon 线程从管道读端逐行读取
    并交给 logging 模块。捕获所有直接写 fd 2 的输出（C 扩展、warnings）。

    Attributes:
        logger_name: logging 模块的 logger 名称
        level: 日志级别（如 logging.ERROR）
    """

    def __init__(self, logger_name: str = "illusion.stderr", level: int = logging.ERROR) -> None:
        self._logger = logging.getLogger(logger_name)
        self._level = level
        self._encoding: str | None = None
        self._installed = False
        self._lock = threading.Lock()
        self._original_fd: int | None = None
        self._read_fd: int | None = None
        self._thread: threading.Thread | None = None

    def install(self) -> None:
        """安装 stderr 重定向。

        流程：os.dup(2) 备份原始 stderr fd → os.pipe() 创建管道 →
        os.dup2(write_fd, 2) 重定向 fd 2 到管道写端 → 启动 daemon 线程
        逐行读取管道并交给 logger。幂等可重复调用。
        """
        with self._lock:
            if self._installed:
                return
            with contextlib.suppress(Exception):
                sys.stderr.flush()
            if self._original_fd is None:
                with contextlib.suppress(OSError):
                    self._original_fd = os.dup(2)
            if self._encoding is None:
                self._encoding = (
                    sys.stderr.encoding or locale.getpreferredencoding(False) or "utf-8"
                )
            read_fd, write_fd = os.pipe()
            os.dup2(write_fd, 2)
            os.close(write_fd)
            self._read_fd = read_fd
            self._thread = threading.Thread(
                target=self._drain, name="illusion-stderr-redirect", daemon=True
            )
            self._thread.start()
            self._installed = True

    def uninstall(self) -> None:
        """卸载 stderr 重定向，恢复原始 fd 2。

        流程：os.dup2(original_fd, 2) 恢复 → join(timeout=2.0) 等 drain
        线程排空残留数据。幂等可重复调用。
        """
        with self._lock:
            if not self._installed:
                return
            if self._original_fd is not None:
                os.dup2(self._original_fd, 2)
            self._installed = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _drain(self) -> None:
        """daemon 线程主循环：逐行读取管道并交给 logger。"""
        buffer = ""
        read_fd = self._read_fd
        if read_fd is None:
            return
        encoding = self._encoding or "utf-8"
        decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
        try:
            while True:
                chunk = os.read(read_fd, 4096)
                if not chunk:
                    break
                buffer += decoder.decode(chunk)
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    self._log_line(line)
        except Exception:
            self._logger.exception("读取重定向 stderr 失败")
        finally:
            buffer += decoder.decode(b"", final=True)
            if buffer:
                self._log_line(buffer)
            with contextlib.suppress(OSError):
                os.close(read_fd)

    def _log_line(self, line: str) -> None:
        """将一行 stderr 输出交给 logger。"""
        text = line.rstrip("\r")
        if not text:
            return
        self._logger.log(self._level, text)

    def open_original_stderr_handle(self) -> IO[bytes] | None:
        """打开原始 stderr 的副本句柄，用于需要写真实 stderr 的场景。"""
        if self._original_fd is None:
            return None
        dup_fd = os.dup(self._original_fd)
        os.set_inheritable(dup_fd, True)
        return os.fdopen(dup_fd, "wb", closefd=True)
