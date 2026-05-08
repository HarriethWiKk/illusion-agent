"""
认证流程模块
============

本模块提供各种提供商类型的认证流程。

每个流程都是一个自包含的类，具有单一的 run() 方法，
执行交互式认证并返回获取的凭据。

类说明：
    - AuthFlow: 认证流程抽象基类
    - ApiKeyFlow: API 密钥认证流程
    - BrowserFlow: 浏览器认证流程

使用示例：
    >>> from illusion.auth.flows import ApiKeyFlow
    >>> flow = ApiKeyFlow(provider="anthropic", prompt_text="Enter API key")
    >>> key = flow.run()
"""

from __future__ import annotations

import logging
import platform
import subprocess
from abc import ABC, abstractmethod

# 模块级日志记录器
log = logging.getLogger(__name__)


class AuthFlow(ABC):
    """认证流程抽象基类
    
    所有认证流程的基类，定义统一的接口。
    """

    @abstractmethod
    def run(self) -> str:
        """执行流程并返回获取的凭据值"""


# ---------------------------------------------------------------------------
# ApiKeyFlow — 直接提示用户输入并存储 API 密钥
# ---------------------------------------------------------------------------


class ApiKeyFlow(AuthFlow):
    """提示用户输入 API 密钥并通过 :mod:`illusion.auth.storage` 持久化
    
    Attributes:
        provider: 提供商名称
        prompt_text: 提示文本
    """

    def __init__(self, provider: str, prompt_text: str | None = None) -> None:
        self.provider = provider
        self.prompt_text = prompt_text or f"Enter your {provider} API key"

    def run(self) -> str:
        """提示用户输入 API 密钥

        Returns:
            str: 输入的 API 密钥

        Raises:
            ValueError: API 密钥为空
        """
        import getpass

        key = getpass.getpass(f"{self.prompt_text}: ").strip()
        if not key:
            raise ValueError("API key cannot be empty.")
        return key


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _try_open_browser(url: str) -> bool:
    """尝试在默认浏览器中打开 URL；如果成功返回 True

    Args:
        url: 要打开的 URL

    Returns:
        bool: 是否成功打开浏览器
    """
    try:
        plat = platform.system()
        if plat == "Darwin":
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if plat == "Windows":
            subprocess.Popen(
                ["start", "", url],
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        # Linux / WSL
        proc = subprocess.Popen(
            ["xdg-open", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            proc.wait(timeout=2)
            return proc.returncode == 0
        except subprocess.TimeoutExpired:
            return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# BrowserFlow — 打开 URL 并等待用户完成认证
# ---------------------------------------------------------------------------


class BrowserFlow(AuthFlow):
    """打开浏览器 URL 并等待用户完成认证

    用户完成浏览器流程后，需要粘贴回令牌/代码 -
    这个简单实现会提示用户输入该值。

    Attributes:
        auth_url: 认证 URL
        prompt_text: 提示文本
    """

    def __init__(self, auth_url: str, prompt_text: str = "Paste the token from your browser") -> None:
        self.auth_url = auth_url
        self.prompt_text = prompt_text

    def run(self) -> str:
        """执行浏览器认证流程

        Returns:
            str: 用户提供的令牌

        Raises:
            ValueError: 未提供令牌
        """
        import getpass

        print(f"Opening browser for authentication: {self.auth_url}", flush=True)
        opened = _try_open_browser(self.auth_url)
        if not opened:
            print(f"Could not open browser automatically. Visit: {self.auth_url}", flush=True)

        token = getpass.getpass(f"{self.prompt_text}: ").strip()
        if not token:
            raise ValueError("No token provided.")
        return token
