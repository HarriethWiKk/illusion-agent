"""
IllusionCode CLI 入口模块
========================

本模块提供 IllusionCode 命令行界面，使用 typer 构建。

主要功能：
    - 交互式会话模式
    - 非交互式打印模式
    - MCP 服务器管理
    - 插件管理
    - 认证管理
    - Cron 任务调度管理

子命令说明：
    - mcp: MCP 服务器管理（list、add、remove）
    - plugin: 插件管理（list、install、uninstall）
    - auth: 认证管理（login、status、logout、switch）
    - cron: Cron 调度管理（start、stop、status、list、toggle、history、logs）

使用示例：
    >>> illusion                    # 启动交互式会话
    >>> illusion -p "你的提示词"     # 非交互式打印模式
    >>> illusion auth login         # 认证登录
    >>> illusion mcp list           # 列出 MCP 服务器
"""

from __future__ import annotations

import json  # JSON 解析和序列化
import sys  # 系统相关功能
from pathlib import Path  # 路径操作
from typing import Any, Optional  # 类型注解

import typer  # CLI 框架

# 确保 Windows 上 stdout/stderr 使用 UTF-8，防止通过 tsx 继承 stdio 管道时的 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 应用程序版本
__version__ = "0.1.1"


def _version_callback(value: bool) -> None:
    """版本回调函数
    
    当用户使用 --version 选项时调用，打印版本号并退出程序。
    
    Args:
        value: 标志位，当前始终为 True
    """
    if value:
        print(f"illusion {__version__}")  # 打印版本信息
        raise typer.Exit()  # 退出程序


# 创建主应用程序
app = typer.Typer(
    name="illusion",
    help=(
        "Illusion Code - AI 驱动的编程助手\n"
        "默认启动交互式会话，使用 -p/--print 进入非交互模式"
    ),
    add_completion=False,
    rich_markup_mode="rich",
    invoke_without_command=True,
)


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

# 创建子命令应用（mcp、plugin、auth、cron）
mcp_app = typer.Typer(name="mcp", help="MCP 服务器管理 / Manage MCP servers")
plugin_app = typer.Typer(name="plugin", help="插件管理 / Manage plugins")
auth_app = typer.Typer(name="auth", help="认证管理 / Manage authentication")
cron_app = typer.Typer(name="cron", help="定时任务管理 / Manage cron scheduler and jobs")
web_app = typer.Typer(name="web", help="启动 Web 界面 / Launch Web UI")

# 注册子命令到主应用
app.add_typer(mcp_app)
app.add_typer(plugin_app)
app.add_typer(auth_app)
app.add_typer(cron_app)
app.add_typer(web_app)


# ---- mcp 子命令 ----

@mcp_app.command("list")
def mcp_list() -> None:
    """列出已配置的 MCP 服务器

    加载当前设置和插件，列出所有已配置的 MCP 服务器及其传输类型。
    """
    from illusion.config import load_settings
    from illusion.mcp.config import load_mcp_server_configs
    from illusion.plugins import load_plugins

    settings = load_settings()
    cwd = str(Path.cwd())
    plugins = load_plugins(settings, cwd)
    configs = load_mcp_server_configs(settings, plugins, cwd)
    if not configs:
        print(_t("mcp_none"))
        return
    for name, cfg in configs.items():
        if hasattr(cfg, "type"):
            transport = cfg.type
            if transport == "stdio":
                cmd = getattr(cfg, "command", "")
                detail = f" ({cmd})" if cmd else ""
            elif transport in ("http", "ws"):
                url = getattr(cfg, "url", "")
                detail = f" ({url})" if url else ""
            else:
                detail = ""
        else:
            transport = "unknown"
            detail = ""
        print(f"  {name}: {transport}{detail}")


@mcp_app.command("add")
def mcp_add(
    name: str = typer.Argument(..., help="Server name"),
    config_json: str = typer.Argument(..., help="Server config as JSON string"),
) -> None:
    """添加 MCP 服务器配置

    Args:
        name: 服务器名称
        config_json: 服务器配置的 JSON 字符串
    """
    from illusion.config import load_settings, save_settings
    from illusion.mcp.types import McpServerConfig

    settings = load_settings()
    try:
        raw = json.loads(config_json)
    except json.JSONDecodeError as exc:
        print(_t("mcp_invalid_json", exc=exc), file=sys.stderr)
        raise typer.Exit(1)
    try:
        cfg = McpServerConfig.model_validate(raw)
    except Exception as exc:
        print(_t("mcp_invalid_config", exc=exc), file=sys.stderr)
        raise typer.Exit(1)
    if not isinstance(settings.mcp_servers, dict):
        settings.mcp_servers = {}
    settings.mcp_servers[name] = cfg
    save_settings(settings)
    print(_t("mcp_added", name=name))


@mcp_app.command("remove")
def mcp_remove(
    name: str = typer.Argument(..., help="Server name to remove"),
) -> None:
    """移除 MCP 服务器配置

    Args:
        name: 要移除的服务器名称
    """
    from illusion.config import load_settings, save_settings

    settings = load_settings()
    if not isinstance(settings.mcp_servers, dict) or name not in settings.mcp_servers:
        print(_t("mcp_not_found", name=name), file=sys.stderr)
        raise typer.Exit(1)
    del settings.mcp_servers[name]
    save_settings(settings)
    print(_t("mcp_removed", name=name))


# ---- plugin 子命令 ----

@plugin_app.command("list")
def plugin_list() -> None:
    """列出已安装的插件"""
    from illusion.config import load_settings
    from illusion.plugins import load_plugins

    settings = load_settings()
    plugins = load_plugins(settings, str(Path.cwd()))
    if not plugins:
        print(_t("plugin_none"))
        return
    for plugin in plugins:
        status = _t("plugin_enabled") if plugin.enabled else _t("plugin_disabled")
        print(f"  {plugin.name} [{status}] - {plugin.description or ''}")


@plugin_app.command("install")
def plugin_install(
    source: str = typer.Argument(..., help="Plugin source (path or URL)"),
) -> None:
    """从源路径安装插件"""
    from illusion.plugins.installer import install_plugin_from_path

    result = install_plugin_from_path(source)
    print(_t("plugin_installed", name=result))


@plugin_app.command("uninstall")
def plugin_uninstall(
    name: str = typer.Argument(..., help="Plugin name to uninstall"),
) -> None:
    """卸载插件"""
    from illusion.plugins.installer import uninstall_plugin

    uninstall_plugin(name)
    print(_t("plugin_uninstalled", name=name))


# ---- cron 子命令（对齐 openclaw cron CLI） ----

@cron_app.command("start")
def cron_start() -> None:
    """启动 cron 调度器"""
    from illusion.services.cron_scheduler import is_scheduler_running, start_daemon

    if is_scheduler_running():
        print(_t("cron_already_running"))
        return
    pid = start_daemon()
    print(_t("cron_started", pid=pid))


@cron_app.command("stop")
def cron_stop() -> None:
    """停止 cron 调度器"""
    from illusion.services.cron_scheduler import stop_scheduler

    if stop_scheduler():
        print(_t("cron_stopped"))
    else:
        print(_t("cron_not_running"))


@cron_app.command("status")
def cron_status_cmd() -> None:
    """显示 cron 调度器状态和任务统计"""
    from illusion.services.cron_scheduler import scheduler_status

    status = scheduler_status()
    state = _t("cron_state_running") if status["running"] else _t("cron_state_stopped")
    print(f"Scheduler: {state}" + (f" (pid={status['pid']})" if status["pid"] else ""))
    print(f"Jobs: {status['enabled_jobs']} {_t('cron_enabled')} / {status['total_jobs']} total")
    print(f"Log: {status['log_file']}")


@cron_app.command("list")
def cron_list_cmd() -> None:
    """列出所有 cron 任务"""
    from illusion.services.cron import load_cron_jobs

    jobs = load_cron_jobs()
    if not jobs:
        print(_t("cron_jobs_none"))
        return
    never = _t("cron_never")
    na = _t("cron_na")
    for job in jobs:
        enabled = "+" if job.get("enabled", True) else "-"
        name = job.get("name", job.get("id", "?"))
        schedule = job.get("schedule", "?")
        recurring = _t("cron_recurring") if job.get("recurring", True) else _t("cron_oneshot")

        last = job.get("last_run", never)
        if last != never:
            last = last[:19]
        last_status = job.get("last_status", "")
        status_indicator = f" [{last_status}]" if last_status else ""

        next_run = job.get("next_run", na)
        if next_run != na:
            next_run = next_run[:19]

        errors = job.get("consecutive_errors", 0)
        error_str = f" [{_t('cron_errors', n=errors)}]" if errors > 0 else ""

        print(f"  [{enabled}] {name}  {schedule} ({recurring})")
        print(f"        {_t('cron_prompt_label')}: {job.get('prompt', '?')[:60]}")
        print(f"        {_t('cron_last_label')}: {last}{status_indicator}  {_t('cron_next_label')}: {next_run}{error_str}")


@cron_app.command("toggle")
def cron_toggle_cmd(
    name: str = typer.Argument(..., help="Job name or ID"),
    enabled: bool = typer.Argument(..., help="true to enable, false to disable"),
) -> None:
    """启用或禁用 cron 任务"""
    from illusion.services.cron import set_job_enabled

    if not set_job_enabled(name, enabled):
        print(_t("cron_job_not_found", name=name))
        raise typer.Exit(1)
    state = _t("cron_enabled") if enabled else _t("cron_disabled")
    print(_t("cron_job_state", name=name, state=state))


@cron_app.command("run")
def cron_run_cmd(
    name: str = typer.Argument(..., help="Job name or ID"),
) -> None:
    """手动触发执行 cron 任务"""
    import asyncio

    from illusion.services.cron import get_cron_job
    from illusion.services.cron_scheduler import execute_job

    job = get_cron_job(name)
    if job is None:
        print(_t("cron_job_not_found", name=name))
        raise typer.Exit(1)

    prompt = job.get("prompt", "")
    if not prompt:
        print(_t("cron_no_prompt", name=name))
        raise typer.Exit(1)

    print(_t("cron_running_job", name=name))
    entry = asyncio.run(execute_job(job))
    status = entry.get("status", "unknown")
    rc = entry.get("returncode", "?")
    print(_t("cron_finished", status=status, rc=rc))

    stdout = entry.get("stdout", "").strip()
    stderr = entry.get("stderr", "").strip()
    if stdout:
        print(f"{_t('cron_output')}\n{stdout}")
    if stderr and status != "success":
        print(f"{_t('cron_error')}\n{stderr}")


@cron_app.command("history")
def cron_history_cmd(
    name: str | None = typer.Argument(None, help="Filter by job name"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of entries"),
) -> None:
    """显示 cron 执行历史记录"""
    from illusion.services.cron_scheduler import load_history

    entries = load_history(limit=limit, job_name=name)
    if not entries:
        print(_t("cron_no_history"))
        return
    for entry in entries:
        ts = entry.get("started_at", "?")[:19]
        status = entry.get("status", "?")
        rc = entry.get("returncode", "?")
        job_name = entry.get("name", "?")
        prompt_preview = entry.get("prompt", "")[:40]
        print(f"  {ts}  {job_name}  {status} (rc={rc})")
        if prompt_preview:
            print(f"    {_t('cron_prompt_label')}: {prompt_preview}")
        stderr = entry.get("stderr", "").strip()
        if stderr and status != "success":
            for line in stderr.splitlines()[:3]:
                print(f"    {_t('cron_error')} {line}")


@cron_app.command("logs")
def cron_logs_cmd(
    lines: int = typer.Option(30, "--lines", "-n", help="Number of lines"),
) -> None:
    """显示 cron 调度器日志"""
    from illusion.config.paths import get_logs_dir

    log_path = get_logs_dir() / "cron_scheduler.log"
    if not log_path.exists():
        print(_t("cron_no_log"))
        return
    content = log_path.read_text(encoding="utf-8", errors="replace")
    tail = content.splitlines()[-lines:]
    for line in tail:
        print(line)


# ---- auth 子命令 ----

# i18n 从共享模块导入
from illusion.config.i18n import MESSAGES as _I18N, t as _t


def _ensure_language() -> str:
    """确保 ui_language 已设置，未设置时让用户选择

    Returns:
        str: 当前 ui_language 值
    """
    from illusion.config import load_settings, save_settings
    settings = load_settings()
    if settings.ui_language:
        return settings.ui_language

    print(_t("select_language"))
    print("  1. 中文 (zh-CN)")
    print("  2. English (en-US)")
    raw = typer.prompt("1/2", default="1")
    lang = "zh-CN" if raw.strip() == "1" else "en-US"
    settings.ui_language = lang
    save_settings(settings)
    return lang


_PROVIDER_OPTIONS: list[tuple[str, dict[str, str]]] = [
    ("custom", _I18N["custom_provider"]),
    ("anthropic", _I18N["anthropic_label"]),
    ("openai", _I18N["openai_label"]),
    ("copilot", _I18N["copilot_label"]),
    ("codex", _I18N["codex_label"]),
]

_API_FORMAT_OPTIONS: list[tuple[str, str]] = [
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
]

_DEFAULT_ENDPOINTS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com/v1",
    "copilot": "https://api.githubcopilot.com",
    "codex": "https://chatgpt.com/backend-api",
}

_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5.4",
    "copilot": "gpt-5.5",
    "codex": "codex-mini",
}


@auth_app.command("login")
def auth_login() -> None:
    """交互式配置提供商认证

    流程：选择提供商 → 认证 → 保存
    Copilot 使用 GitHub OAuth 设备码流程，其他提供商使用 API 密钥。
    """
    from illusion.auth.flows import ApiKeyFlow
    from illusion.auth.manager import AuthManager
    from illusion.auth.storage import store_env_credential

    _ensure_language()
    manager = AuthManager()

    # 1. 选择提供商
    print(_t("select_provider"))
    for i, (key, labels) in enumerate(_PROVIDER_OPTIONS, 1):
        lang = manager.settings.ui_language or "en-US"
        label = labels.get(lang, labels.get("en-US", key))
        print(f"  {i}. {label}")
    raw = typer.prompt(_t("enter_number"), default="1")
    try:
        idx = int(raw.strip()) - 1
        if 0 <= idx < len(_PROVIDER_OPTIONS):
            provider_choice = _PROVIDER_OPTIONS[idx][0]
        else:
            print(_t("invalid_selection"), file=sys.stderr)
            raise typer.Exit(1)
    except ValueError:
        print(_t("invalid_selection"), file=sys.stderr)
        raise typer.Exit(1)

    # --- Copilot 走设备码 OAuth 流程 ---
    if provider_choice == "copilot":
        _copilot_login(manager)
        return

    # --- Codex 走外部 CLI 凭据读取流程 ---
    if provider_choice == "codex":
        _codex_login(manager)
        return

    # --- 其他提供商走 API 密钥流程 ---

    # 2. 确定 API 格式
    if provider_choice == "anthropic":
        api_format = "anthropic"
    elif provider_choice == "openai":
        api_format = "openai"
    else:
        # 自定义提供商：让用户选择 API 格式
        print(_t("select_api_format"))
        for i, (fmt, label) in enumerate(_API_FORMAT_OPTIONS, 1):
            print(f"  {i}. {label}")
        raw = typer.prompt(_t("enter_number"), default="1")
        try:
            idx = int(raw.strip()) - 1
            if 0 <= idx < len(_API_FORMAT_OPTIONS):
                api_format = _API_FORMAT_OPTIONS[idx][0]
            else:
                print(_t("invalid_selection"), file=sys.stderr)
                raise typer.Exit(1)
        except ValueError:
            print(_t("invalid_selection"), file=sys.stderr)
            raise typer.Exit(1)

    # 3. 输入端点
    default_ep = _DEFAULT_ENDPOINTS.get(provider_choice, "")
    if default_ep:
        prompt_text = f"{_t('enter_endpoint')} ({_t('default_endpoint')}: {default_ep}): "
        endpoint = input(prompt_text).strip()
        if not endpoint:
            endpoint = default_ep
    else:
        endpoint = input(f"{_t('enter_endpoint')}: ").strip()
        if not endpoint:
            print(_t("endpoint_required"), file=sys.stderr)
            raise typer.Exit(1)

    # 4. 输入 API 密钥
    flow = ApiKeyFlow(prompt_text=_t("enter_api_key"))
    try:
        api_key = flow.run()
    except ValueError:
        print(_t("api_key_required"), file=sys.stderr)
        raise typer.Exit(1)

    # 5. 输入模型名称
    default_model = _DEFAULT_MODELS.get(provider_choice, "")
    if default_model:
        prompt_text = f"{_t('enter_model')} ({_t('default_endpoint')}: {default_model}): "
        model_name = input(prompt_text).strip()
        if not model_name:
            model_name = default_model
    else:
        model_name = input(f"{_t('enter_model')}: ").strip()
        if not model_name:
            print(_t("model_required"), file=sys.stderr)
            raise typer.Exit(1)

    # 6. 分配 env_N 并保存
    envs = manager.list_envs()
    if envs:
        # 找到下一个可用的 env_N
        existing_nums = []
        for k in envs:
            try:
                existing_nums.append(int(k.split("_")[1]))
            except (ValueError, IndexError):
                pass
        next_num = max(existing_nums, default=0) + 1
    else:
        next_num = 1
    env_key = f"env_{next_num}"

    # 保存到 settings.json
    env_config = {
        "api_format": api_format,
        "base_url": endpoint,
        "api_key": "",  # 不在 settings.json 中存储实际密钥
        "model_1": model_name,
    }
    setattr(manager.settings, env_key, env_config)
    manager.settings.model = f"{env_key}:model_1"
    manager.save_settings()

    # 保存密钥到 credentials.json
    store_env_credential(env_key, "api_key", api_key)

    print(_t("env_saved", env_key=env_key))


def _copilot_login(manager: Any) -> None:
    """Copilot 设备码 OAuth 认证流程

    Args:
        manager: AuthManager 实例
    """
    import time

    from illusion.auth.copilot import CopilotAuth
    from illusion.auth.storage import store_env_credential

    copilot = CopilotAuth()

    # 1. 启动设备码流程
    try:
        flow = copilot.start_device_flow()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)

    # 2. 显示用户码和验证 URL
    print(_t("copilot_open_url"))
    print(f"  {flow['verification_uri']}")
    print(_t("copilot_enter_code", code=flow["user_code"]))
    print()
    print(_t("copilot_waiting"))

    # 3. 轮询等待授权
    try:
        success = copilot.poll_for_token(flow["device_code"])
    except RuntimeError as exc:
        msg = str(exc)
        if "过期" in msg or "expired" in msg.lower():
            print(_t("copilot_device_expired"), file=sys.stderr)
        elif "拒绝" in msg or "denied" in msg.lower():
            print(_t("copilot_auth_denied"), file=sys.stderr)
        elif "订阅" in msg or "subscription" in msg.lower():
            print(_t("copilot_no_subscription"), file=sys.stderr)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)

    if not success:
        print(_t("copilot_device_expired"), file=sys.stderr)
        raise typer.Exit(1)

    status = copilot.get_status()
    username = status.get("username") or ""
    print(_t("copilot_auth_success", user=username))

    # 4. 输入模型名称
    default_model = _DEFAULT_MODELS.get("copilot", "gpt-5.5")
    prompt_text = f"{_t('enter_model')} ({_t('default_endpoint')}: {default_model}): "
    model_name = input(prompt_text).strip()
    if not model_name:
        model_name = default_model

    # 5. 分配 env_N 并保存
    envs = manager.list_envs()
    if envs:
        existing_nums = []
        for k in envs:
            try:
                existing_nums.append(int(k.split("_")[1]))
            except (ValueError, IndexError):
                pass
        next_num = max(existing_nums, default=0) + 1
    else:
        next_num = 1
    env_key = f"env_{next_num}"

    env_config = {
        "api_format": "openai",
        "base_url": _DEFAULT_ENDPOINTS["copilot"],
        "api_key": "",
        "model_1": model_name,
        "provider": "copilot",
    }
    setattr(manager.settings, env_key, env_config)
    manager.settings.model = f"{env_key}:model_1"
    manager.save_settings()

    print(_t("env_saved", env_key=env_key))


def _codex_login(manager: Any) -> None:
    """Codex 外部 CLI 凭据读取流程

    从 ~/.codex/auth.json 读取已由 Codex CLI 管理的认证信息。

    Args:
        manager: AuthManager 实例
    """
    from illusion.auth.external import default_binding_for_provider, load_external_credential
    from illusion.auth.storage import store_env_credential

    # 1. 检查 Codex CLI 认证是否存在
    binding = default_binding_for_provider("openai_codex")
    try:
        cred = load_external_credential(binding)
    except (ValueError, FileNotFoundError):
        print(_t("codex_not_found"), file=sys.stderr)
        raise typer.Exit(1)

    username = cred.profile_label or cred.value[:8] + "..."
    print(_t("codex_auth_success", user=username))

    # 2. 输入模型名称
    default_model = _DEFAULT_MODELS.get("codex", "codex-mini")
    prompt_text = f"{_t('enter_model')} ({_t('default_endpoint')}: {default_model}): "
    model_name = input(prompt_text).strip()
    if not model_name:
        model_name = default_model

    # 3. 分配 env_N 并保存
    envs = manager.list_envs()
    if envs:
        existing_nums = []
        for k in envs:
            try:
                existing_nums.append(int(k.split("_")[1]))
            except (ValueError, IndexError):
                pass
        next_num = max(existing_nums, default=0) + 1
    else:
        next_num = 1
    env_key = f"env_{next_num}"

    env_config = {
        "api_format": "openai",
        "base_url": _DEFAULT_ENDPOINTS["codex"],
        "api_key": "",
        "model_1": model_name,
        "provider": "codex",
    }
    setattr(manager.settings, env_key, env_config)
    manager.settings.model = f"{env_key}:model_1"
    manager.save_settings()

    print(_t("env_saved", env_key=env_key))


@auth_app.command("status")
def auth_status_cmd() -> None:
    """显示所有环境的认证状态"""
    from illusion.auth.manager import AuthManager

    _ensure_language()
    manager = AuthManager()
    statuses = manager.get_env_credential_statuses()

    if not statuses:
        print(_t("no_envs"))
        return

    print(_t("env_status_title"))

    # 列宽
    col_env = 10
    col_format = 12
    col_model = 28
    col_endpoint = 36
    col_cred = 10

    header = (
        f"{_t('col_env'):<{col_env}} "
        f"{_t('col_format'):<{col_format}} "
        f"{_t('col_model'):<{col_model}} "
        f"{_t('col_endpoint'):<{col_endpoint}} "
        f"{_t('col_credential'):<{col_cred}} "
    )
    print(header)
    print("-" * len(header))

    for name, info in statuses.items():
        cred_str = _t("configured") if info["has_credential"] else _t("missing")
        active_str = f" {_t('active_mark')}" if info["active"] else ""
        ep = info["base_url"] or "-"
        print(
            f"{name:<{col_env}} "
            f"{info['api_format']:<{col_format}} "
            f"{info['model']:<{col_model}} "
            f"{ep:<{col_endpoint}} "
            f"{cred_str:<{col_cred}} "
            f"{active_str}"
        )


@auth_app.command("logout")
def auth_logout(
    env_key: Optional[str] = typer.Argument(None, help="Environment to clear (e.g. env_1)"),
) -> None:
    """清除环境的已存储凭据

    Args:
        env_key: 要清除的环境，默认交互式选择
    """
    from illusion.auth.manager import AuthManager

    _ensure_language()
    manager = AuthManager()

    if env_key is None:
        envs = manager.list_envs()
        if not envs:
            print(_t("no_envs"))
            raise typer.Exit(1)
        print(_t("select_env_to_logout"))
        env_keys = list(envs.keys())
        for i, k in enumerate(env_keys, 1):
            print(f"  {i}. {k}")
        raw = typer.prompt(_t("enter_number"), default="1")
        try:
            idx = int(raw.strip()) - 1
            if 0 <= idx < len(env_keys):
                env_key = env_keys[idx]
            else:
                print(_t("invalid_selection"), file=sys.stderr)
                raise typer.Exit(1)
        except ValueError:
            print(_t("invalid_selection"), file=sys.stderr)
            raise typer.Exit(1)

    manager.clear_env_api_key(env_key)
    print(_t("credential_cleared", env_key=env_key))


@auth_app.command("switch")
def auth_switch(
    env_key: Optional[str] = typer.Argument(None, help="Environment to switch to (e.g. env_1)"),
) -> None:
    """切换活动环境

    Args:
        env_key: 要切换的环境，无参数时交互式选择
    """
    from illusion.auth.manager import AuthManager

    _ensure_language()
    manager = AuthManager()

    if env_key is None:
        envs = manager.list_envs()
        if not envs:
            print(_t("no_envs"))
            raise typer.Exit(1)
        print(_t("select_env_to_switch"))
        env_keys = list(envs.keys())
        for i, k in enumerate(env_keys, 1):
            print(f"  {i}. {k}")
        raw = typer.prompt(_t("enter_number"), default="1")
        try:
            idx = int(raw.strip()) - 1
            if 0 <= idx < len(env_keys):
                env_key = env_keys[idx]
            else:
                print(_t("invalid_selection"), file=sys.stderr)
                raise typer.Exit(1)
        except ValueError:
            print(_t("invalid_selection"), file=sys.stderr)
            raise typer.Exit(1)

    try:
        manager.use_env(env_key)
    except ValueError:
        print(_t("env_not_found", env_key=env_key), file=sys.stderr)
        raise typer.Exit(1)
    print(_t("switched_to", env_key=env_key))


@auth_app.command("add-model")
def auth_add_model(
    env_key: str = typer.Argument(..., help="Environment key (e.g. env_1)"),
    model_name: str = typer.Argument(..., help="Model name to add"),
) -> None:
    """在已有的 env_N 中增加模型（model_N）

    Args:
        env_key: 环境键名，如 env_1
        model_name: 要添加的模型名称
    """
    from illusion.auth.manager import AuthManager

    _ensure_language()
    manager = AuthManager()

    env = manager.settings.get_env(env_key)
    if env is None:
        print(_t("env_not_found", env_key=env_key), file=sys.stderr)
        raise typer.Exit(1)

    # 找到下一个可用的 model_N 编号
    existing = []
    for k in env.list_models():
        try:
            existing.append(int(k.split("_")[1]))
        except (ValueError, IndexError):
            pass
    next_num = max(existing, default=0) + 1
    model_key = f"model_{next_num}"

    # 写入配置
    env_config = env.model_dump()
    env_config[model_key] = model_name
    setattr(manager.settings, env_key, env_config)
    manager.save_settings()

    print(_t("model_added", env_key=env_key, model_key=model_key, model_name=model_name))


# ---- web 子命令 ----


@web_app.callback(invoke_without_command=True)
def web_start(
    port: int = typer.Option(3000, "--port", "-p", help="Web 服务端口"),
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
    dev: bool = typer.Option(False, "--dev", help="开发模式（启用 CORS，不 serve 静态文件）"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="指定模型"),
    prompt: Optional[str] = typer.Option(None, "--prompt", help="初始提示词"),
) -> None:
    """启动 Illusion Code Web 界面 / Launch Illusion Code Web UI"""
    import threading
    import uvicorn
    from illusion.config.settings import load_settings
    from illusion.ui.web.server import create_app
    from illusion.ui.web.ws_host import WebHostConfig

    settings = load_settings()
    resolved_model = model or settings.model

    config = WebHostConfig(
        model=resolved_model,
        effort=getattr(settings, "effort", None),
    )

    app = create_app(dev=dev, host_config=config)

    url = f"http://{host}:{port}"
    typer.echo(f"Illusion Code Web UI: {url}")
    if not dev:
        import webbrowser
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")


# ---------------------------------------------------------------------------
# 主命令
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit",
        callback=_version_callback,
        is_eager=True,
    ),
    # --- Session ---
    continue_session: bool = typer.Option(
        False,
        "--continue",
        "-c",
        help="Continue the most recent conversation in the current directory",
        rich_help_panel="Session",
    ),
    resume: str | None = typer.Option(
        None,
        "--resume",
        "-r",
        help="Resume a conversation by session ID, or open picker",
        rich_help_panel="Session",
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        "-n",
        help="Set a display name for this session",
        rich_help_panel="Session",
    ),
    # --- Model & Effort ---
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Model alias (e.g. 'sonnet', 'opus') or full model ID",
        rich_help_panel="Model & Effort",
    ),
    effort: str | None = typer.Option(
        None,
        "--effort",
        help="Effort level for the session (low, medium, high, max)",
        rich_help_panel="Model & Effort",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Override verbose mode setting from config",
        rich_help_panel="Model & Effort",
    ),
    max_turns: int | None = typer.Option(
        None,
        "--max-turns",
        help="Maximum number of agentic turns (useful with --print)",
        rich_help_panel="Model & Effort",
    ),
    # --- Output ---
    print_mode: str | None = typer.Option(
        None,
        "--print",
        "-p",
        help="Print response and exit. Pass your prompt as the value: -p 'your prompt'",
        rich_help_panel="Output",
    ),
    output_format: str | None = typer.Option(
        None,
        "--output-format",
        help="Output format with --print: text (default), json, or stream-json",
        rich_help_panel="Output",
    ),
    # --- Permissions ---
    permission_mode: str | None = typer.Option(
        None,
        "--permission-mode",
        help="Permission mode: default, plan, or full_auto",
        rich_help_panel="Permissions",
    ),
    dangerously_skip_permissions: bool = typer.Option(
        False,
        "--dangerously-skip-permissions",
        help="Bypass all permission checks (only for sandboxed environments)",
        rich_help_panel="Permissions",
    ),
    allowed_tools: Optional[list[str]] = typer.Option(
        None,
        "--allowed-tools",
        help="Comma or space-separated list of tool names to allow",
        rich_help_panel="Permissions",
    ),
    disallowed_tools: Optional[list[str]] = typer.Option(
        None,
        "--disallowed-tools",
        help="Comma or space-separated list of tool names to deny",
        rich_help_panel="Permissions",
    ),
    # --- System & Context ---
    system_prompt: str | None = typer.Option(
        None,
        "--system-prompt",
        "-s",
        help="Override the default system prompt",
        rich_help_panel="System & Context",
    ),
    append_system_prompt: str | None = typer.Option(
        None,
        "--append-system-prompt",
        help="Append text to the default system prompt",
        rich_help_panel="System & Context",
    ),
    settings_file: str | None = typer.Option(
        None,
        "--settings",
        help="Path to a JSON settings file or inline JSON string",
        rich_help_panel="System & Context",
    ),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="Anthropic-compatible API base URL",
        rich_help_panel="System & Context",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        "-k",
        help="API key (overrides config and environment)",
        rich_help_panel="System & Context",
    ),
    bare: bool = typer.Option(
        False,
        "--bare",
        help="Minimal mode: skip hooks, plugins, MCP, and auto-discovery",
        rich_help_panel="System & Context",
    ),
    api_format: str | None = typer.Option(
        None,
        "--api-format",
        help="API format: 'anthropic' (default) or 'openai' (DashScope, GitHub Models, etc.)",
        rich_help_panel="System & Context",
    ),
    # --- Advanced ---
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug logging",
        rich_help_panel="Advanced",
    ),
    mcp_config: Optional[list[str]] = typer.Option(
        None,
        "--mcp-config",
        help="Load MCP servers from JSON files or strings",
        rich_help_panel="Advanced",
    ),
    cwd: str = typer.Option(
        str(Path.cwd()),
        "--cwd",
        help="Working directory for the session",
        hidden=True,
    ),
    backend_only: bool = typer.Option(
        False,
        "--backend-only",
        help="Run the structured backend host for the React terminal UI",
        hidden=True,
    ),
) -> None:
    """主入口函数：启动交互式会话或运行单个提示词
    
    支持多种运行模式：
    - 交互式会话模式（默认）
    - 非交互式打印模式（使用 -p/--print）
    - 继续会话（使用 --continue 或 --resume）
    
    Args:
        ctx: Typer 上下文对象
        version: 显示版本号选项
        continue_session: 继续最近会话选项
        resume: 通过会话 ID 恢复会话选项
        name: 会话显示名称
        model: 模型别名或完整模型 ID
        effort: 会话努力级别
        verbose: 覆盖详细输出模式设置
        max_turns: 最大代理轮次数
        print_mode: 打印模式提示词
        output_format: 输出格式
        permission_mode: 权限模式
        dangerously_skip_permissions: 跳过权限检查
        allowed_tools: 允许的工具列表
        disallowed_tools: 禁止的工具列表
        system_prompt: 覆盖默认系统提示词
        append_system_prompt: 追加到默认系统提示词
        settings_file: 设置文件路径
        base_url: Anthropic 兼容 API 基础 URL
        api_key: API 密钥
        bare: 最小模式
        api_format: API 格式
        debug: 启用调试日志
        mcp_config: 从 JSON 文件或字符串加载 MCP 服务器
        cwd: 会话工作目录
        backend_only: 运行结构化后端主机
    """
    if ctx.invoked_subcommand is not None:  # 如果调用了子命令，直接返回
        return

    import asyncio  # 异步编程模块

    if dangerously_skip_permissions:  # 如果跳过权限检查
        permission_mode = "full_auto"  # 设置为完全自动模式

    from illusion.ui.app import run_print_mode, run_repl  # 导入 UI 模块

    # 处理 --continue 和 --resume 标志
    if continue_session or resume is not None:
        from illusion.services.session_storage import (  # 导入会话存储模块
            list_session_snapshots,  # 列出会话快照
            load_session_by_id,  # 按 ID 加载会话
            load_session_snapshot,  # 加载会话快照
        )

        session_data = None  # 会话数据
        if continue_session:
            session_data = load_session_snapshot(cwd)
            if session_data is None:
                print(_t("session_not_found_prev"), file=sys.stderr)
                raise typer.Exit(1)
            print(_t("session_continuing", summary=session_data.get('summary', '(?)')[:60]))
        elif resume == "" or resume is None:
            sessions = list_session_snapshots(cwd, limit=10)
            if not sessions:
                print(_t("session_no_saved"), file=sys.stderr)
                raise typer.Exit(1)
            print(_t("session_saved_list"))
            for i, s in enumerate(sessions, 1):
                print(f"  {i}. [{s['session_id']}] {s.get('summary', '?')[:50]} ({_t('session_msg_count', n=s['message_count'])})")
            choice = typer.prompt(_t("session_enter_id"))
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(sessions):
                    session_data = load_session_by_id(cwd, sessions[idx]["session_id"])
                else:
                    print(_t("invalid_selection"), file=sys.stderr)
                    raise typer.Exit(1)
            except ValueError:
                session_data = load_session_by_id(cwd, choice)
            if session_data is None:
                print(_t("session_not_found", id=choice), file=sys.stderr)
                raise typer.Exit(1)
        else:
            session_data = load_session_by_id(cwd, resume)
            if session_data is None:
                print(_t("session_not_found", id=resume), file=sys.stderr)
                raise typer.Exit(1)

        # 将会话传递给 REPL
        asyncio.run(
            run_repl(
                prompt=None,  # 无提示词，使用恢复的会话
                cwd=cwd,  # 工作目录
                model=session_data.get("model") or model,  # 模型
                backend_only=backend_only,  # 仅后端模式
                base_url=base_url,  # 基础 URL
                system_prompt=session_data.get("system_prompt") or system_prompt,  # 系统提示词
                api_key=api_key,  # API 密钥
                restore_messages=session_data.get("messages"),  # 恢复的消息
                restore_session_id=session_data.get("session_id"),
                effort=effort,  # 推理强度级别
            )
        )
        return

    # 打印模式处理
    if print_mode is not None:
        prompt = print_mode.strip()
        if not prompt:
            print(_t("print_requires_prompt"), file=sys.stderr)
            raise typer.Exit(1)
        # 运行打印模式
        asyncio.run(
            run_print_mode(
                prompt=prompt,  # 提示词
                output_format=output_format or "text",  # 输出格式
                cwd=cwd,  # 工作目录
                model=model,  # 模型
                base_url=base_url,  # 基础 URL
                system_prompt=system_prompt,  # 系统提示词
                append_system_prompt=append_system_prompt,  # 追加系统提示词
                api_key=api_key,  # API 密钥
                api_format=api_format,  # API 格式
                permission_mode=permission_mode,  # 权限模式
                max_turns=max_turns,  # 最大轮次
                effort=effort,  # 推理强度级别
            )
        )
        return

    # 启动交互式 REPL 会话
    asyncio.run(
        run_repl(
            prompt=None,  # 无初始提示词
            cwd=cwd,  # 工作目录
            model=model,  # 模型
            max_turns=max_turns,  # 最大轮次
            backend_only=backend_only,  # 仅后端模式
            base_url=base_url,  # 基础 URL
            system_prompt=system_prompt,  # 系统提示词
            api_key=api_key,  # API 密钥
            api_format=api_format,  # API 格式
            effort=effort,  # 推理强度级别
        )
    )
