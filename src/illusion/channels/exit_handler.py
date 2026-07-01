"""共享退出处理器
==================

统一 Ctrl+C / 正常退出时的守护进程退出行为，消除 cli.py 中
main() 和 web_start() 重复的内联退出确认逻辑。

行为规则：
    1. 守护进程未运行 → 直接返回（程序正常退出）
    2. channels.json 无配置或无启用渠道 → 直接返回
    3. 否则弹出确认提示：
       - 输入 y/Y/yes/回车（空输入）→ 停止守护进程
       - 输入期间再次 Ctrl+C（KeyboardInterrupt）→ 停止守护进程
       - 其他任何输入 → 不停止（守护进程保留运行）
       - EOF（非 TTY 环境，如管道）→ 不停止

函数说明：
    - handle_daemon_exit_on_interrupt: 退出时调用，按上述规则处理
    - _confirm_exit: 私有确认函数

使用示例：
    >>> from illusion.channels.exit_handler import handle_daemon_exit_on_interrupt
    >>> # 在 cli.py 的 finally 块中调用
    >>> handle_daemon_exit_on_interrupt()
"""
from __future__ import annotations

from illusion.channels import (
    is_channel_daemon_running,
    stop_channel_daemon_by_pid,
)
from illusion.channels.config import load_channels_config


def handle_daemon_exit_on_interrupt() -> None:
    """Ctrl+C 或正常退出时的守护进程退出处理

    行为：
    1. 守护进程未运行 → 直接返回（程序正常退出）
    2. channels.json 无配置或无启用渠道 → 直接返回
    3. 否则弹出确认提示：
       - 输入 y/Y/yes/回车（空输入）→ 停止守护进程
       - 输入期间再次 Ctrl+C（KeyboardInterrupt）→ 停止守护进程
       - 其他任何输入 → 不停止（守护进程保留运行）

    退出路径必须比正常路径更健壮：任何异常（如 channels.json 权限不足、
    PID 文件读取失败）都不应破坏退出体验，静默吞掉并记日志。
    """
    try:
        if not is_channel_daemon_running():
            return
        cfg = load_channels_config()
        if not cfg.has_enabled_channels():
            return
        if _confirm_exit():
            stop_channel_daemon_by_pid()
    except Exception:  # noqa: BLE001
        # 退出路径防御性兜底：避免配置文件异常/PID 读取失败等导致丑陋 traceback
        import logging
        logging.getLogger(__name__).debug("exit handler suppressed exception", exc_info=True)


def _confirm_exit() -> bool:
    """确认是否退出守护进程

    y/Y/yes/空回车/二次 Ctrl+C 均视为确认；
    其他输入或 EOF 视为拒绝。

    Returns:
        bool: True 表示确认停止守护进程
    """
    from illusion.config.i18n import t

    try:
        answer = input(t("channel_daemon_exit_prompt") + " ").strip()
        return answer.lower() in ("", "y", "yes")
    except KeyboardInterrupt:
        # 再次 Ctrl+C = 确认退出。Windows 终端会回显 "^C" 到屏幕，
        # 打印明确的确认信息让用户知道 Ctrl+C 已被正确处理
        print()
        print(t("channel_daemon_exit_confirmed"))
        return True
    except EOFError:
        return False  # 非 TTY 环境（如管道）默认不杀
