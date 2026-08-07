#!/usr/bin/env python3
"""
内置 Python 运行时下载脚本
============================

从 astral-sh/python-build-standalone 下载 install_only 发行版，
解压到 desktop/resources/python/<plat-arch>/。

用法：
    python scripts/fetch_python.py                  # 默认 3.12.7
    python scripts/fetch_python.py --version 3.11.9

下载源：https://github.com/astral-sh/python-build-standalone/releases
解压使用 Python 标准库 tarfile（跨平台兼容）。

路径约定：
    DESKTOP_ROOT = desktop/
    输出: DESKTOP_ROOT/resources/python/<plat-arch>/
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

DESKTOP_ROOT = Path(__file__).resolve().parent.parent / "desktop"
RESOURCES = DESKTOP_ROOT / "resources"

DEFAULT_VERSION = "3.12.13"

# python-build-standalone 命名约定的平台三元组
TRIPLE_MAP = {
    ("win32", "x64"): "x86_64-pc-windows-msvc",
    ("win32", "arm64"): "aarch64-pc-windows-msvc",
    ("darwin", "arm64"): "aarch64-apple-darwin",
    ("darwin", "x64"): "x86_64-apple-darwin",
    ("linux", "x64"): "x86_64-unknown-linux-gnu",
    ("linux", "arm64"): "aarch64-unknown-linux-gnu",
}

# 桌面壳内部用的平台-arch 标识（与 runtime.ts platArch 保持一致）
PLAT_ARCH_MAP = {
    "win32": "win",
    "darwin": "mac",
    "linux": "linux",
}


def triple() -> str:
    """平台三元组（python-build-standalone 命名约定）"""
    # 统一用 platform.machine() 并规范化 arch：x86_64/amd64 → x64，aarch64 → arm64
    import platform
    mach = platform.machine().lower()
    arch = "arm64" if mach in ("arm64", "aarch64") else "x64"
    key = (sys.platform, arch)
    result = TRIPLE_MAP.get(key)
    if result is None:
        print(f"不支持的平台：{key[0]}-{key[1]}", file=sys.stderr)
        sys.exit(1)
    return result


def plat_arch() -> str:
    """桌面壳内部用的平台-arch 标识"""
    import platform
    plat = PLAT_ARCH_MAP.get(sys.platform, "linux")
    mach = platform.machine().lower()
    arch = "arm64" if mach in ("arm64", "aarch64") else "x64"
    return f"{plat}-{arch}"


def find_asset(version: str) -> tuple[str, str]:
    """查 GitHub release 找匹配 version + 平台的 install_only asset"""
    triple_str = triple()
    suffix = f"{triple_str}-install_only.tar.gz"
    url = "https://api.github.com/repos/astral-sh/python-build-standalone/releases?per_page=20"
    req = urllib.request.Request(url, headers={"User-Agent": "illusion-agent-desktop"})
    with urllib.request.urlopen(req) as resp:
        if resp.status != 200:
            print(f"GitHub API 请求失败：{resp.status}", file=sys.stderr)
            sys.exit(1)
        releases = json.loads(resp.read())
    for rel in releases:
        for asset in rel.get("assets", []):
            name = asset["name"]
            if f"cpython-{version}" in name and name.endswith(suffix):
                return asset["browser_download_url"], name
    print(f"未找到 Python {version} 的 {triple_str} install_only 资产", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="下载内置 Python 运行时")
    parser.add_argument("--version", default=DEFAULT_VERSION, help=f"Python 版本（默认 {DEFAULT_VERSION}）")
    args = parser.parse_args()

    url, name = find_asset(args.version)
    out_dir = RESOURCES / "python" / plat_arch()
    out_dir.mkdir(parents=True, exist_ok=True)
    tarball = out_dir / name

    print(f"下载 {name}\n  {url}")
    urllib.request.urlretrieve(url, tarball)

    print(f"解压到 {out_dir}")
    with tarfile.open(tarball, "r:gz") as tf:
        # filter='tar'：拒绝绝对路径/.. 但保留 symlinks（install_only 含 python3→python3.12 等符号链接）
        tf.extractall(out_dir, filter='tar')

    tarball.unlink()
    print(f"Python {args.version} -> {out_dir}")


if __name__ == "__main__":
    main()
