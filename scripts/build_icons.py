#!/usr/bin/env python3
"""
图标构建脚本
=============

从 desktop/build/assets/ 的源图标生成各平台所需图标到 desktop/build/：
  - Windows: icon.ico（直接复制）
  - Linux:   icon.png（复制 512x512）
  - macOS:   icon.icns（用 iconutil，仅 mac 平台可执行）

同时复制一份 512 png 到 desktop/resources/icon.png，作为运行时托盘图标
（打包后由 extraResources 放入 Resources/，运行时 process.resourcesPath/icon.png）。

用法：python scripts/build_icons.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

DESKTOP_ROOT = Path(__file__).resolve().parent.parent / "desktop"
ASSETS = DESKTOP_ROOT / "build" / "assets"
BUILD = DESKTOP_ROOT / "build"
RESOURCES = DESKTOP_ROOT / "resources"


def main() -> None:
    if not ASSETS.exists():
        print(f"图标源目录不存在：{ASSETS}", file=sys.stderr)
        sys.exit(1)

    BUILD.mkdir(parents=True, exist_ok=True)
    RESOURCES.mkdir(parents=True, exist_ok=True)

    # --- Windows: 复制 ico ---
    ico_src = ASSETS / "icon.ico"
    if ico_src.exists():
        shutil.copy2(ico_src, BUILD / "icon.ico")
        print("icon.ico")
    else:
        print("警告: 未找到源 icon.ico", file=sys.stderr)

    # --- Linux / 运行时托盘: 复制 512 png ---
    png512 = ASSETS / "icon_512x512.png"
    if png512.exists():
        shutil.copy2(png512, BUILD / "icon.png")
        shutil.copy2(png512, RESOURCES / "icon.png")
        print("icon.png (build + resources)")
    else:
        print("警告: 未找到源 icon_512x512.png", file=sys.stderr)

    # --- macOS: iconutil 生成 icns（仅 mac 平台可执行）---
    if sys.platform == "darwin":
        iconset = BUILD / "icon.iconset"
        if iconset.exists():
            shutil.rmtree(iconset)
        iconset.mkdir(parents=True)

        sizes = [16, 32, 128, 256, 512]
        for s in sizes:
            dest1 = iconset / f"icon_{s}x{s}.png"
            dest2 = iconset / f"icon_{s}x{s}@2x.png"
            src1 = ASSETS / f"icon_{s}x{s}.png"
            src2 = ASSETS / f"icon_{s * 2}x{s * 2}.png"
            if src1.exists():
                shutil.copy2(src1, dest1)
            if src2.exists():
                shutil.copy2(src2, dest2)
            elif src1.exists():
                # 回退：用 1x 充当 @2x
                shutil.copy2(src1, dest2)
                print(f"警告: icon_{s}x{s}@2x.png 缺失，用 {s}x{s} 回退", file=sys.stderr)

        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(BUILD / "icon.icns")],
            check=True,
        )
        shutil.rmtree(iconset)
        print("icon.icns")
    else:
        print("icon.icns 需在 macOS 上生成（CI mac runner 会处理）")


if __name__ == "__main__":
    main()
