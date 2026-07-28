"""Windows Job Objects 沙箱测试"""
import sys

import pytest

from illusion.sandbox.platforms.base import SandboxPlatformConfig


def test_windows_platform_has_correct_type():
    """验证 Windows 平台类存在且继承正确"""
    from illusion.sandbox.platforms.base import SandboxPlatform
    from illusion.sandbox.platforms.windows import WindowsSandboxPlatform
    assert issubclass(WindowsSandboxPlatform, SandboxPlatform)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 专用测试")
def test_windows_platform_check_dependencies():
    from illusion.sandbox.platforms.windows import WindowsSandboxPlatform
    platform = WindowsSandboxPlatform()
    deps = platform.check_dependencies()
    assert isinstance(deps, list)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 专用测试")
def test_windows_wrap_returns_list():
    from illusion.sandbox.platforms.windows import WindowsSandboxPlatform
    platform = WindowsSandboxPlatform()
    config = SandboxPlatformConfig(allow_write=["."], deny_write=[], deny_read=[], allow_read=[])
    result = platform.wrap_command(["cmd", "/c", "echo hello"], config)
    assert isinstance(result, list)
    assert result == ["cmd", "/c", "echo hello"]
    # 沙箱句柄存储在实例中
    assert platform.get_last_sandbox_result() is not None
    assert platform.get_last_sandbox_result().job_handle is not None
