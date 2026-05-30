"""
Hatch 构建钩子
=============

在 wheel 构建前自动执行前端构建（npm install + npm run build）。
需要 Node.js 18+ 环境。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """在 wheel 构建前自动构建 terminal 和 web 前端。"""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        """在构建开始前执行前端构建。"""
        root = Path(self.root)
        npm = shutil.which("npm")
        if npm is None:
            raise RuntimeError(
                "Node.js/npm is not installed. "
                "Please install Node.js 18+ from https://nodejs.org/ "
                "to build the frontend assets."
            )

        self._build_frontend(root, npm, "terminal")
        self._build_frontend(root, npm, "web")

    def _build_frontend(self, root: Path, npm: str, name: str) -> None:
        """构建单个前端。"""
        frontend_dir = root / "frontend" / name
        if not (frontend_dir / "package.json").exists():
            print(f"hatch_build: skipping {name} (no package.json)")
            return

        print(f"hatch_build: building {name} frontend...")

        # npm install
        if not (frontend_dir / "node_modules").exists():
            self._run([npm, "install", "--no-fund", "--no-audit"], frontend_dir)

        # npm run build
        self._run([npm, "run", "build"], frontend_dir)

    def _run(self, cmd: list[str], cwd: Path) -> None:
        """运行命令，失败时抛出异常。"""
        result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"Command failed: {' '.join(cmd)}\n"
                f"stdout: {result.stdout[-500:]}\n"
                f"stderr: {result.stderr[-500:]}"
            )
