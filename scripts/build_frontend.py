#!/usr/bin/env python3
"""
前端统一构建脚本
================

构建 terminal 和/或 web 前端的预编译产物。

用法：
    python scripts/build_frontend.py             # 构建两者
    python scripts/build_frontend.py --terminal  # 只构建 terminal
    python scripts/build_frontend.py --web       # 只构建 web
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _find_node() -> str:
    """查找 node 可执行文件路径。"""
    node = shutil.which("node")
    if node is None:
        print("ERROR: Node.js is not installed or not in PATH.", file=sys.stderr)
        print("  Please install Node.js 18+ from https://nodejs.org/", file=sys.stderr)
        sys.exit(1)
    return node


def _find_npm() -> str:
    """查找 npm 可执行文件路径。"""
    npm = shutil.which("npm")
    if npm is None:
        print("ERROR: npm is not installed or not in PATH.", file=sys.stderr)
        sys.exit(1)
    return npm


def _run(cmd: list[str], cwd: Path) -> None:
    """运行命令并检查返回码。"""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode != 0:
        print(f"ERROR: Command failed with exit code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)


def _ensure_deps(frontend_dir: Path, npm: str) -> None:
    """如果 node_modules 不存在则运行 npm install。"""
    if not (frontend_dir / "node_modules").exists():
        print(f"  Installing dependencies in {frontend_dir.name}...")
        _run([npm, "install", "--no-fund", "--no-audit"], frontend_dir)
    else:
        print(f"  Dependencies already installed in {frontend_dir.name}.")


def build_terminal(npm: str) -> None:
    """构建 terminal 前端（esbuild bundle）。"""
    frontend_dir = REPO_ROOT / "frontend" / "terminal"
    if not (frontend_dir / "package.json").exists():
        print(f"SKIP: Terminal frontend not found at {frontend_dir}")
        return

    print("\n=== Building terminal frontend ===")
    _ensure_deps(frontend_dir, npm)
    _run([npm, "run", "build"], frontend_dir)

    dist = frontend_dir / "dist" / "index.mjs"
    if dist.exists():
        size_kb = dist.stat().st_size / 1024
        print(f"  OK: {dist} ({size_kb:.0f} KB)")
    else:
        print("ERROR: Build output not found: dist/index.mjs", file=sys.stderr)
        sys.exit(1)


def build_web(npm: str) -> None:
    """构建 web 前端（Vite build）。"""
    frontend_dir = REPO_ROOT / "frontend" / "web"
    if not (frontend_dir / "package.json").exists():
        print(f"SKIP: Web frontend not found at {frontend_dir}")
        return

    print("\n=== Building web frontend ===")
    _ensure_deps(frontend_dir, npm)
    _run([npm, "run", "build"], frontend_dir)

    index_html = frontend_dir / "dist" / "index.html"
    if index_html.exists():
        print(f"  OK: {frontend_dir / 'dist'}")
    else:
        print("ERROR: Build output not found: dist/index.html", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build illusion-code frontends")
    parser.add_argument("--terminal", action="store_true", help="Build terminal frontend only")
    parser.add_argument("--web", action="store_true", help="Build web frontend only")
    args = parser.parse_args()

    build_both = not args.terminal and not args.web

    _find_node()
    npm = _find_npm()

    if build_both or args.terminal:
        build_terminal(npm)
    if build_both or args.web:
        build_web(npm)

    print("\nAll builds completed.")


if __name__ == "__main__":
    main()
