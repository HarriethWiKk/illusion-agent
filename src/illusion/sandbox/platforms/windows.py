"""Windows 平台沙箱实现 — Job Objects + Restricted Tokens

使用 Windows 内核机制实现进程隔离：
- Job Objects: 进程树管理、内存限制、终止保证
- Restricted Tokens: 移除特权、防止令牌逃逸
- Low Integrity Level: 阻止写入高完整性目录
"""
from __future__ import annotations
import ctypes
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any
from .base import SandboxPlatform, SandboxPlatformConfig


# Windows API 常量
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JobObjectExtendedLimitInformation = 9
TOKEN_ALL_ACCESS = 0xF01FF
DISABLE_MAX_PRIVILEGE = 0x1
SANDBOX_INERT = 0x2
CREATE_SUSPENDED = 0x00000004
PROCESS_ALL_ACCESS = 0x1F0FFF
TOKEN_MANDATORY_LABEL = 25
SE_GROUP_INTEGRITY = 0x00000020
LOW_INTEGRITY_SID = "S-1-16-4096"


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    """Job Object 基本限制信息结构体"""
    _fields_ = [
        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class IO_COUNTERS(ctypes.Structure):
    """IO 计数器结构体"""
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    """Job Object 扩展限制信息结构体"""
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


@dataclass
class WindowsSandboxResult:
    """Windows 沙箱进程包装结果

    Attributes:
        command: 原始命令
        job_handle: Job Object 句柄
        restricted_token: 受限令牌句柄
        creation_flags: 进程创建标志
    """
    command: list[str]
    job_handle: int
    restricted_token: int
    creation_flags: int = CREATE_SUSPENDED


class WindowsSandboxPlatform(SandboxPlatform):
    """Windows Job Objects + Restricted Tokens 沙箱平台"""

    def __init__(self) -> None:
        self._last_sandbox_result: WindowsSandboxResult | None = None

    def check_dependencies(self) -> list[str]:
        """检查 pywin32 是否可用"""
        errors = []
        if sys.platform != "win32":
            errors.append("Windows 沙箱仅在 Windows 平台可用")
            return errors
        try:
            import win32job  # noqa: F401
            import win32security  # noqa: F401
            import win32process  # noqa: F401
            import win32api  # noqa: F401
        except ImportError:
            errors.append("缺少 pywin32，请安装: pip install pywin32")
        return errors

    def wrap_command(
        self, command: list[str], config: SandboxPlatformConfig
    ) -> list[str]:
        """准备沙箱环境并返回命令

        Windows 的沙箱通过 Job Object + Restricted Token 实现，
        不需要像 Linux/macOS 那样包装命令。沙箱句柄存储在实例中，
        供后续进程创建使用。

        Returns:
            原始命令列表（Windows 不包装命令本身）
        """
        if sys.platform != "win32":
            raise RuntimeError("WindowsSandboxPlatform 仅在 Windows 上可用")

        import win32job
        import win32security
        import win32api
        import win32con

        # 1. 创建 Job Object
        job_handle = win32job.CreateJobObject(
            None, f"IllusionSandbox_{id(command)}"
        )
        info = win32job.QueryInformationJobObject(
            job_handle, win32job.JobObjectExtendedLimitInformation
        )
        info["BasicLimitInformation"]["LimitFlags"] = (
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | JOB_OBJECT_LIMIT_JOB_MEMORY
        )
        info["BasicLimitInformation"]["ActiveProcessLimit"] = 8
        info["ProcessMemoryLimit"] = 512 * 1024 * 1024  # 512MB
        info["JobMemoryLimit"] = 1024 * 1024 * 1024  # 1GB
        win32job.SetInformationJobObject(
            job_handle, win32job.JobObjectExtendedLimitInformation, info
        )

        # 2. 创建受限令牌
        current_token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(), win32con.TOKEN_ALL_ACCESS
        )
        restricted_token = win32security.CreateRestrictedToken(
            current_token,
            win32security.DISABLE_MAX_PRIVILEGE | win32security.SANDBOX_INERT,
            None, None, None,
        )

        # 3. 设置 Low Integrity Level
        low_integrity_sid = win32security.ConvertStringSidToSid(LOW_INTEGRITY_SID)
        win32security.SetTokenInformation(
            restricted_token,
            win32security.TokenIntegrityLevel,
            (low_integrity_sid, SE_GROUP_INTEGRITY),
        )

        # 存储沙箱句柄供进程创建使用
        self._last_sandbox_result = WindowsSandboxResult(
            command=command,
            job_handle=job_handle,
            restricted_token=restricted_token,
        )

        # 返回原始命令（Windows 不包装命令本身）
        return command

    def get_last_sandbox_result(self) -> WindowsSandboxResult | None:
        """获取最近一次创建的沙箱结果"""
        return self._last_sandbox_result

    def cleanup_after_command(self) -> None:
        """Job Object 句柄关闭时自动清理"""
        pass
