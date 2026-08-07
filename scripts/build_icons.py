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
import struct
import subprocess
import sys
from pathlib import Path

DESKTOP_ROOT = Path(__file__).resolve().parent.parent / "desktop"
ASSETS = DESKTOP_ROOT / "build" / "assets"
BUILD = DESKTOP_ROOT / "build"
RESOURCES = DESKTOP_ROOT / "resources"


def _png_size(data: bytes) -> tuple[int, int]:
    """从 PNG 文件头解析宽高（8 字节签名 + IHDR chunk）。"""
    # PNG 签名(8) + 长度(4) + "IHDR"(4) + 宽(4) + 高(4)
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是有效的 PNG 文件")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def build_ico_from_pngs() -> bool:
    """从 assets/ 下的多分辨率 PNG 合成 icon.ico，写入 build/ 和 assets/

    不依赖 PIL：assets 中的 PNG 已是目标尺寸，直接以原始字节嵌入
    ICO 条目（ICO 格式支持 PNG 压缩图像），避免 CI 环境额外安装 Pillow。
    """
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    images: list[bytes] = []
    for size in sizes:
        path = ASSETS / f"icon_{size}x{size}.png"
        if not path.exists():
            print(f"警告: 缺少 {path.name}", file=sys.stderr)
            return False
        data = path.read_bytes()
        try:
            w, h = _png_size(data)
        except ValueError as exc:
            print(f"错误: {path.name} 不是有效 PNG: {exc}", file=sys.stderr)
            return False
        images.append(data)
        if w != size or h != size:
            print(f"警告: {path.name} 实际尺寸 {w}x{h}，与文件名 {size} 不符", file=sys.stderr)

    # 构建 ICO 文件：头部 + 目录 + 数据
    header = struct.pack("<HHH", 0, 1, len(images))
    directory = b""
    data_blocks = b""
    offset = 6 + len(images) * 16
    for size, data in zip(sizes, images):
        w = size if size < 256 else 0
        h = size if size < 256 else 0
        directory += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        data_blocks += data
        offset += len(data)

    ico_bytes = header + directory + data_blocks
    (BUILD / "icon.ico").write_bytes(ico_bytes)
    (ASSETS / "icon.ico").write_bytes(ico_bytes)
    print(f"icon.ico ({len(images)} resolutions, {len(ico_bytes)} bytes)")
    return True


def main() -> None:
    if not ASSETS.exists():
        print(f"图标源目录不存在：{ASSETS}", file=sys.stderr)
        sys.exit(1)

    BUILD.mkdir(parents=True, exist_ok=True)
    RESOURCES.mkdir(parents=True, exist_ok=True)

    # --- Windows: 从多分辨率 PNG 合成 ico ---
    if not build_ico_from_pngs():
        # 回退：直接复制旧 ico
        ico_src = ASSETS / "icon.ico"
        if ico_src.exists():
            shutil.copy2(ico_src, BUILD / "icon.ico")
            print("icon.ico (fallback copy)")
        else:
            print("错误: 无法生成 icon.ico", file=sys.stderr)
            sys.exit(1)

    # --- Linux / 运行时托盘: 复制 512 png ---
    png512 = ASSETS / "icon_512x512.png"
    if png512.exists():
        shutil.copy2(png512, BUILD / "icon.png")
        shutil.copy2(png512, RESOURCES / "icon.png")
        shutil.copy2(png512, ASSETS / "icon.png")
        print("icon.png (build + resources + assets)")
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
