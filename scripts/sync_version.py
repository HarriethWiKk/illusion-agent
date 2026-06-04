"""
版本同步脚本
============

从 pyproject.toml 读取版本号，生成前端版本文件。

使用方法：
    python scripts/sync_version.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


def read_version_from_pyproject() -> str:
    """从 pyproject.toml 读取版本号"""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    version = data.get("project", {}).get("version")
    if not version:
        raise ValueError("Version not found in pyproject.toml")

    return version


def generate_terminal_version_file(version: str) -> None:
    """生成终端前端版本文件"""
    content = f"""/**
 * 版本信息模块
 *
 * 此文件由 scripts/sync_version.py 自动生成，请勿手动修改。
 * 版本号来源于 pyproject.toml。
 */

/** 当前版本号 */
export const VERSION = '{version}';
"""
    output_path = Path(__file__).parent.parent / "frontend" / "terminal" / "src" / "version.ts"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"Generated: {output_path}")


def generate_web_version_file(version: str) -> None:
    """生成 Web 前端版本文件"""
    content = f"""/**
 * 版本信息模块
 *
 * 此文件由 scripts/sync_version.py 自动生成，请勿手动修改。
 * 版本号来源于 pyproject.toml。
 */

/** 当前版本号 */
export const VERSION = '{version}';
"""
    output_path = Path(__file__).parent.parent / "frontend" / "web" / "src" / "version.ts"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"Generated: {output_path}")


def update_package_json_version(package_path: Path, version: str) -> None:
    """更新 package.json 中的版本号"""
    if not package_path.exists():
        print(f"Warning: {package_path} not found, skipping")
        return

    with package_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("version") == version:
        print(f"Version already up to date: {package_path}")
        return

    data["version"] = version
    with package_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Updated version in: {package_path}")


def main() -> None:
    """主函数"""
    version = read_version_from_pyproject()
    print(f"Version from pyproject.toml: {version}")

    generate_terminal_version_file(version)
    generate_web_version_file(version)

    # 更新 package.json 版本号
    root = Path(__file__).parent.parent
    update_package_json_version(root / "frontend" / "web" / "package.json", version)
    update_package_json_version(root / "frontend" / "terminal" / "package.json", version)

    print("Version sync completed successfully.")


if __name__ == "__main__":
    main()
