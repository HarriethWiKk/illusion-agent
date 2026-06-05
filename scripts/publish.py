"""
发布脚本
========

构建并发布 illusion-code 到 PyPI 或 TestPyPI。

用法：
    python scripts/publish.py              # 发布到 PyPI
    python scripts/publish.py --test       # 发布到 TestPyPI
    python scripts/publish.py --dry-run    # 只构建+校验，不上传

依赖：
    pip install build twine
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None) -> None:
    """运行命令，失败时退出。"""
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=False)
    if result.returncode != 0:
        print(f"\nERROR: Command failed with exit code {result.returncode}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="构建并发布 illusion-code")
    parser.add_argument("--test", action="store_true", help="发布到 TestPyPI")
    parser.add_argument("--dry-run", action="store_true", help="只构建+校验，不上传")
    parser.add_argument("--skip-tests", action="store_true", help="跳过测试")
    parser.add_argument("--skip-lint", action="store_true", help="跳过 lint 检查")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    dist_dir = root / "dist"

    # 检查依赖
    for tool in ("build", "twine"):
        if shutil.which(tool) is None and not args.dry_run:
            print(f"ERROR: '{tool}' not found. Install with: pip install build twine")
            sys.exit(1)

    # Step 1: Lint
    if not args.skip_lint:
        print("\n=== Running lint check ===")
        run([sys.executable, "-m", "ruff", "check", "src/"], cwd=root)

    # Step 2: Tests
    if not args.skip_tests:
        print("\n=== Running tests ===")
        run([sys.executable, "-m", "pytest", "tests/", "-x", "-q"], cwd=root)

    # Step 3: Clean dist
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir()

    # Step 4: Build
    print("\n=== Building sdist + wheel ===")
    run([sys.executable, "-m", "build"], cwd=root)

    # Step 5: Check
    print("\n=== Checking package ===")
    run([sys.executable, "-m", "twine", "check", "dist/*"], cwd=root)

    # Step 6: Upload
    if args.dry_run:
        print("\n=== Dry run complete. Package contents: ===")
        for f in sorted(dist_dir.iterdir()):
            print(f"  {f.name}")
        print("\nTo publish, run without --dry-run")
        return

    repo_name = "TestPyPI" if args.test else "PyPI"
    print(f"\n=== Uploading to {repo_name} ===")
    cmd = [sys.executable, "-m", "twine", "upload"]
    if args.test:
        cmd.extend(["--repository", "testpypi"])
    cmd.append("dist/*")
    run(cmd, cwd=root)

    print(f"\nPublished to {repo_name} successfully!")


if __name__ == "__main__":
    main()
