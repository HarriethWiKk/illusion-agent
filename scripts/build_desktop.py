#!/usr/bin/env python3
"""
桌面壳构建统一入口
====================

整合运行时下载、后端预装、图标生成、发行包构建的 CLI 入口。

用法：
    python scripts/build_desktop.py              # 运行所有步骤（一键打包）
    python scripts/build_desktop.py --fetch      # 仅下载运行时
    python scripts/build_desktop.py --install    # 仅预装后端到内置 Python
    python scripts/build_desktop.py --icons      # 仅生成图标
    python scripts/build_desktop.py --dist       # 仅构建发行包（需先 fetch + install + icons）
    python scripts/build_desktop.py --all        # fetch + install + icons + dist
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
DESKTOP_DIR = REPO_ROOT / "desktop"


def _resolve_cmd(cmd: list[str]) -> list[str]:
    """Windows 上将 .cmd/.bat 路径补全，避免 WinError 193。"""
    if sys.platform == "win32" and not cmd[0].endswith((".cmd", ".bat", ".exe")):
        for ext in (".cmd", ".bat", ".exe"):
            candidate = cmd[0] + ext
            if Path(candidate).exists():
                cmd = [candidate] + cmd[1:]
                break
    return cmd


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    """运行命令并检查返回码。"""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=False)
    if result.returncode != 0:
        print(f"ERROR: Command failed with exit code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)


def fetch_runtimes() -> None:
    """下载内置 Python + Node 运行时"""
    print("\n=== Downloading runtimes ===")
    _run([sys.executable, str(SCRIPTS_DIR / "fetch_python.py")])
    _run([sys.executable, str(SCRIPTS_DIR / "fetch_node.py")])


def build_icons() -> None:
    """生成桌面壳图标"""
    print("\n=== Building icons ===")
    _run([sys.executable, str(SCRIPTS_DIR / "build_icons.py")])


def _plat_arch() -> str:
    """计算当前平台-arch 标识（与 fetch_python.py 保持一致）"""
    import platform
    plat_map = {"win32": "win", "darwin": "mac", "linux": "linux"}
    plat = plat_map.get(sys.platform, "linux")
    mach = platform.machine().lower()
    arch = "arm64" if mach in ("arm64", "aarch64") else "x64"
    return f"{plat}-{arch}"


def install_backend() -> None:
    """将 illusion 包及全量依赖预装到内置 Python（让无环境用户解压即用）"""
    print("\n=== Installing backend into bundled Python ===")

    # 检测前端 dist 存在（pyproject force-include 需要，缺失则打包进 wheel 的是空目录）
    web_dist = REPO_ROOT / "frontend" / "web" / "dist"
    terminal_dist = REPO_ROOT / "frontend" / "terminal" / "dist"
    if not web_dist.exists() or not terminal_dist.exists():
        print("ERROR: 前端 dist 缺失，请先构建前端：python scripts/build_frontend.py", file=sys.stderr)
        sys.exit(1)

    # 穷举内置 python 可执行路径（与 runtime.ts bundledPythonPath 布局一致）
    python_dir = DESKTOP_DIR / "resources" / "python" / _plat_arch() / "python"
    candidates = [
        python_dir / "python.exe",                    # win: python/python.exe
        python_dir / "python3",                       # unix: python/python3
        python_dir / "install" / "bin" / "python",    # unix install_only: python/install/bin/python
        python_dir / "install" / "bin" / "python3",
    ]
    python_exe = next((p for p in candidates if p.exists()), None)
    if python_exe is None:
        print(f"ERROR: 内置 Python 不存在于 {python_dir}\n请先运行 --fetch 下载运行时", file=sys.stderr)
        sys.exit(1)

    # 安装项目根的 illusion[all]（含 feishu/weixin optional 全量依赖）
    _run([
        str(python_exe), "-m", "pip", "install",
        "--no-input", "--disable-pip-version-check",
        f"{REPO_ROOT}[all]",
    ])


def build_dist() -> None:
    """编译 TypeScript + electron-builder 打包"""
    print("\n=== Building distribution ===")
    npm = shutil.which("npm")
    if npm is None:
        print("ERROR: npm not found in PATH", file=sys.stderr)
        sys.exit(1)

    # 确保依赖已安装（检测 electron 是否存在）
    node_modules = DESKTOP_DIR / "node_modules"
    if not (node_modules / "electron" / "package.json").exists():
        print("  Installing npm dependencies...")
        _run(_resolve_cmd([npm, "install", "--no-fund", "--no-audit"]), cwd=DESKTOP_DIR)

    # 编译 TypeScript + 打包
    _run(_resolve_cmd([npm, "run", "dist"]), cwd=DESKTOP_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(description="桌面壳构建工具")
    parser.add_argument("--fetch", action="store_true", help="仅下载运行时")
    parser.add_argument("--install", action="store_true", help="仅预装后端到内置 Python")
    parser.add_argument("--icons", action="store_true", help="仅生成图标")
    parser.add_argument("--dist", action="store_true", help="仅构建发行包")
    parser.add_argument("--all", action="store_true", help="执行所有步骤（fetch + install + icons + dist）")
    args = parser.parse_args()

    # 默认行为：如果没有指定任何 flag，执行 --all
    if not (args.fetch or args.install or args.icons or args.dist or args.all):
        args.all = True

    if args.all:
        fetch_runtimes()
        install_backend()
        build_icons()
        build_dist()
    else:
        if args.fetch:
            fetch_runtimes()
        if args.install:
            install_backend()
        if args.icons:
            build_icons()
        if args.dist:
            build_dist()

    print("\nDone.")


if __name__ == "__main__":
    main()
