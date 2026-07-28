"""
杂项斜杠命令
============

/exit, /version, /copy, /export, /share, /feedback,
/help, /hooks, /reload-plugins, /skills, /files, /continue
"""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from illusion import __version__
from illusion.commands.helpers import copy_to_clipboard, last_message_text
from illusion.commands.types import CommandContext, CommandResult
from illusion.config.paths import get_feedback_log_path
from illusion.config.settings import load_settings
from illusion.plugins.loader import load_plugins
from illusion.services import export_session_markdown
from illusion.skills.loader import load_skill_registry


async def exit_handler(_: str, context: CommandContext) -> CommandResult:
    """退出程序"""
    del context
    return CommandResult(should_exit=True)


async def version_handler(_: str, context: CommandContext) -> CommandResult:
    """显示版本号"""
    del context
    try:
        version = importlib.metadata.version("illusion-code")
    except importlib.metadata.PackageNotFoundError:
        version = __version__
    return CommandResult(message=f"IllusionCode {version}")


async def copy_handler(args: str, context: CommandContext) -> CommandResult:
    """复制最新回复或指定文本"""
    text = args.strip() or last_message_text(context.engine.messages)
    if not text:
        return CommandResult(message="Nothing to copy.")
    copied, target = copy_to_clipboard(text)
    if copied:
        return CommandResult(message=f"Copied {len(text)} characters to the clipboard.")
    return CommandResult(message=f"Clipboard unavailable. Saved copied text to {target}")


async def export_handler(_: str, context: CommandContext) -> CommandResult:
    """导出当前转录"""
    path = export_session_markdown(cwd=context.cwd, messages=context.engine.messages)
    return CommandResult(message=f"Exported transcript to {path}")


async def share_handler(_: str, context: CommandContext) -> CommandResult:
    """创建可分享的转录快照"""
    path = export_session_markdown(cwd=context.cwd, messages=context.engine.messages)
    return CommandResult(message=f"Created shareable transcript snapshot at {path}")


async def feedback_handler(args: str, context: CommandContext) -> CommandResult:
    """保存 CLI 反馈"""
    del context
    path = get_feedback_log_path()
    if not args.strip():
        return CommandResult(message=f"Feedback log: {path}\nUsage: /feedback TEXT")
    timestamp = datetime.now(UTC).isoformat()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {args.strip()}\n")
    return CommandResult(message=f"Saved feedback to {path}")


def make_help_handler(registry: Any) -> Any:
    """创建 help 命令处理器（需要引用 registry 实例）"""

    async def help_handler(args: str, context: CommandContext) -> CommandResult:
        """显示可用命令"""
        return CommandResult(message=registry.help_text())

    return help_handler


async def hooks_handler(_: str, context: CommandContext) -> CommandResult:
    """显示已配置的 hooks"""
    return CommandResult(message=context.hooks_summary or "No hooks configured.")


async def reload_plugins_handler(_: str, context: CommandContext) -> CommandResult:
    """重新加载插件"""
    settings = load_settings()
    plugins = load_plugins(settings, context.cwd)
    if not plugins:
        return CommandResult(message="No plugins discovered.")
    lines = ["Reloaded plugins:"]
    for plugin in plugins:
        state = "enabled" if plugin.enabled else "disabled"
        lines.append(f"- {plugin.manifest.name} [{state}]")
    return CommandResult(message="\n".join(lines))


async def skills_handler(args: str, context: CommandContext) -> CommandResult:
    """列出或显示可用技能"""
    from illusion.skills.loader import get_project_skills_dir, get_user_skills_dir

    skill_registry = load_skill_registry(context.cwd)
    skills = skill_registry.list_skills()

    if not skills:
        return CommandResult(message="No skills available.")

    tokens = args.strip().split()

    # /skills — 列出所有技能
    if not tokens:
        user_skills_dir = get_user_skills_dir()
        project_skills_dir = get_project_skills_dir(context.cwd)
        lines = ["Available skills:", ""]
        if user_skills_dir.exists():
            lines.append(f"User skills directory: {user_skills_dir}")
        if project_skills_dir.exists():
            lines.append(f"Project skills directory: {project_skills_dir}")
        lines.append("")
        for i, skill in enumerate(skills, 1):
            source = f" [{skill.source}]"
            first_line = skill.description.split("\n", 1)[0][:60] if skill.description else "(empty)"
            lines.append(f"  {i}. {skill.name}{source}  —  {first_line}")
        lines.append("")
        lines.append("Usage: /skills <name|number>  — view a specific skill")
        return CommandResult(message="\n".join(lines))

    # /skills <name|number> — 显示指定技能内容
    target = tokens[0]
    selected = None

    # 按序号查找
    try:
        idx = int(target) - 1
        if 0 <= idx < len(skills):
            selected = skills[idx]
    except ValueError:
        pass

    # 按名称查找
    if selected is None:
        for skill in skills:
            if skill.name.lower() == target.lower():
                selected = skill
                break

    if selected is None:
        return CommandResult(message=f"Skill not found: {target}. Use /skills to list available skills.")

    return CommandResult(message=selected.content)


async def files_handler(args: str, context: CommandContext) -> CommandResult:
    """列出当前工作区文件"""
    raw = args.strip()
    root = Path(context.cwd)
    max_items = 30
    tokens = raw.split(maxsplit=1)
    if tokens and tokens[0] == "dirs":
        dirs = [
            path
            for path in sorted(root.rglob("*"))
            if path.is_dir() and ".git" not in path.parts and ".venv" not in path.parts
        ]
        lines = [str(path.relative_to(root)) for path in dirs[:max_items]]
        if len(dirs) > max_items:
            lines.append(f"... {len(dirs) - max_items} more")
        return CommandResult(message="\n".join(lines) if lines else "(no directories)")
    if tokens and tokens[0].isdigit():
        max_items = max(1, min(int(tokens[0]), 200))
        raw = tokens[1] if len(tokens) == 2 else ""
    needle = raw.lower()
    files = [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.parts and ".venv" not in path.parts
    ]
    if needle:
        files = [path for path in files if needle in str(path.relative_to(root)).lower()]
    lines = [str(path.relative_to(root)) for path in files[:max_items]]
    if len(files) > max_items:
        lines.append(f"... {len(files) - max_items} more")
    return CommandResult(
        message="\n".join(lines) if lines else "(no matching files)"
    )


def _check_pypi_latest() -> str | None:
    """查询 PyPI 获取 illusion-code 最新版本号

    Returns:
        str | None: 最新版本号，查询失败返回 None
    """
    try:
        resp = httpx.get(
            "https://pypi.org/pypi/illusion-code/json",
            timeout=10,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return str(resp.json()["info"]["version"])
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


def _get_current_version() -> str:
    """获取当前安装的 illusion-code 版本号

    Returns:
        str: 当前版本号
    """
    try:
        return importlib.metadata.version("illusion-code")
    except importlib.metadata.PackageNotFoundError:
        return __version__


def _run_pip_upgrade(packages: list[str]) -> tuple[bool, str]:
    """执行 pip install --upgrade

    Args:
        packages: 要升级的包名列表

    Returns:
        tuple[bool, str]: (是否成功, 输出信息)
    """
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", *packages]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, "pip upgrade timed out"
    except OSError as exc:
        return False, str(exc)


def _run_pip_install(pkgs: list[str]) -> tuple[bool, str]:
    """通过 pip install 安装指定包（渠道依赖首次配置时调用）

    复用 _run_pip_upgrade 的子进程调用模式，但使用 install 子命令（不带 --upgrade）。

    Args:
        pkgs: 要安装的包名列表（含版本约束）

    Returns:
        tuple[bool, str]: (是否成功, 输出文本)
    """
    cmd = [sys.executable, "-m", "pip", "install", *pkgs]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, "pip install timed out"
    except OSError as exc:
        return False, str(exc)


async def update_handler(args: str, context: CommandContext) -> CommandResult:
    """检查并更新 IllusionCode"""
    from illusion.config.i18n import t

    del context
    include_deps = "--deps" in args

    # 1. 获取当前版本
    current = _get_current_version()

    # 2. 查询 PyPI 最新版本
    print(t("update_checking"))
    latest = _check_pypi_latest()

    if latest is None:
        # PyPI 查询失败，降级为直接升级
        print(t("update_network_error"))
        print(t("update_installing"))
        ok, output = _run_pip_upgrade(["illusion-code"])
        if ok:
            new_ver = _get_current_version()
            return CommandResult(message=t("update_success", version=new_ver))
        return CommandResult(message=t("update_failed", error=output[:200]))

    # 3. 版本对比
    if latest == current:
        msg = t("update_latest", version=current)
        if not include_deps:
            return CommandResult(message=msg)
        # 即使已是最新，如果指定了 --deps 仍继续检查依赖
        print(msg)
    else:
        print(t("update_available", current=current, latest=latest))
        print(t("update_confirm"))
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            return CommandResult(message="Cancelled.")

        print(t("update_installing"))
        ok, output = _run_pip_upgrade(["illusion-code"])
        if ok:
            print(t("update_success", version=latest))
        else:
            return CommandResult(message=t("update_failed", error=output[:200]))

    # 4. 依赖更新
    if include_deps:
        print(t("update_deps_checking"))
        # 从 pyproject.toml 读取依赖包名
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[no-redef]

        pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if not pyproject_path.exists():
            pyproject_path = Path.cwd() / "pyproject.toml"

        if pyproject_path.exists():
            with pyproject_path.open("rb") as f:
                data = tomllib.load(f)
            deps = data.get("project", {}).get("dependencies", [])
            # 提取包名（去掉版本约束）
            pkg_names = []
            for dep in deps:
                name = dep.split(">=")[0].split("==")[0].split("<=")[0].split("~=")[0].split("[")[0].strip()
                pkg_names.append(name)

            if pkg_names:
                print(t("update_deps_available"))
                for pkg in pkg_names:
                    print(f"  - {pkg}")
                print(t("update_deps_confirm"))
                try:
                    input()
                except (KeyboardInterrupt, EOFError):
                    return CommandResult(message="Cancelled.")

                ok, output = _run_pip_upgrade(pkg_names)
                if ok:
                    return CommandResult(message=t("update_deps_success"))
                return CommandResult(message=t("update_failed", error=output[:200]))

    return CommandResult(message="")


async def continue_handler(args: str, context: CommandContext) -> CommandResult:
    """继续被中断的工具循环"""
    raw = args.strip()
    if not context.engine.has_pending_continuation():
        return CommandResult(message="Nothing to continue (no pending tool results).")

    turns: int | None = None
    if raw:
        tokens = raw.split()
        if tokens[0] == "set" and len(tokens) == 2:
            raw = tokens[1]
        try:
            turns = int(raw)
        except ValueError:
            return CommandResult(message="Usage: /continue [COUNT]")
        turns = max(1, min(turns, 512))

    return CommandResult(
        message="Continuing pending tool loop...",
        continue_pending=True,
        continue_turns=turns,
    )
