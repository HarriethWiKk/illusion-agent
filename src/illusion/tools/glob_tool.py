"""
文件系统Glob工具模块
====================

本模块提供基于glob模式的文件搜索功能。

主要功能：
    - 快速的文件模式匹配工具，支持任意大小的代码库
    - 支持glob模式如 "**/*.js" 或 "src/**/*.ts"
    - 返回按修改时间排序的匹配文件路径
    - 使用ripgrep的文件遍历器（可用时），尊重.gitignore并可跳过重目录

类说明：
    - GlobToolInput: Glob工具输入参数
    - GlobTool: Glob工具类

函数说明：
    - _resolve_path: 解析路径
    - _looks_like_git_repo: 判断是否像Git仓库
    - _glob: 异步glob实现

使用示例：
    >>> # 查找所有Python文件
    >>> pattern = "**/*.py"
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult


class GlobToolInput(BaseModel):
    """Glob工具的参数模型
    
    Attributes:
        pattern: 相对于工作目录的glob模式
        root: 可选的搜索根目录
        limit: 返回结果数量限制
    """

    pattern: str = Field(description="Glob pattern relative to the working directory")
    root: str | None = Field(default=None, description="Optional search root")
    limit: int = Field(default=200, ge=1, le=5000)


class GlobTool(BaseTool):
    """列出匹配glob模式的文件
    
    使用说明：
    - 快速的文件模式匹配工具，适用于任何规模的代码库
    - 支持glob模式如 "**/*.js" 或 "src/**/*.ts"
    - 返回按修改时间排序的匹配文件路径
    - 当需要按名称模式查找文件时使用此工具
    - 当进行开放性搜索可能需要多轮glob和grep时，使用Agent工具
    """

    name = "glob"
    description = """- Fast file pattern matching tool that works with any codebase size
- Supports glob patterns like "**/*.js" or "src/**/*.ts"
- Returns matching file paths sorted by modification time
- Use this tool when you need to find files by name patterns
- When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead"""
    input_model = GlobToolInput

    def is_read_only(self, arguments: GlobToolInput) -> bool:
        """返回工具是否为只读操作
        
        Args:
            arguments: 工具输入参数
        
        Returns:
            bool: 始终返回True，glob是只读操作
        """
        del arguments
        return True

    async def execute(self, arguments: GlobToolInput, context: ToolExecutionContext) -> ToolResult:
        """执行glob搜索
        
        Args:
            arguments: 工具输入参数
            context: 工具执行上下文
        
        Returns:
            ToolResult: 搜索结果
        """
        # 解析根目录路径
        root = _resolve_path(context.cwd, arguments.root) if arguments.root else context.cwd
        pattern = arguments.pattern
        # 兼容绝对 glob 模式（例如 "E:\\repo\\**\\*.py"）
        if arguments.root is None:
            split_root_pattern = _split_absolute_glob_pattern(arguments.pattern)
            if split_root_pattern is not None:
                root, pattern = split_root_pattern
        # 执行异步glob搜索
        matches = await _glob(root, pattern, limit=arguments.limit)
        if not matches:
            return ToolResult(output="(no matches)")
        return ToolResult(output="\n".join(matches))


def _resolve_path(base: Path, candidate: str | None) -> Path:
    """解析相对路径为绝对路径
    
    Args:
        base: 基础路径
        candidate: 候选路径字符串
    
    Returns:
        Path: 解析后的绝对路径
    """
    path = Path(candidate or ".").expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _split_absolute_glob_pattern(pattern: str) -> tuple[Path, str] | None:
    """拆分绝对 glob 模式为根目录和相对模式。

    Args:
        pattern: 可能包含通配符的模式

    Returns:
        tuple[Path, str] | None: (root, relative_pattern) 或 None
    """
    candidate = Path(pattern).expanduser()
    if not candidate.is_absolute():
        return None

    parts = list(candidate.parts)
    wildcard_index = -1
    for index, part in enumerate(parts):
        if any(token in part for token in ("*", "?", "[")):
            wildcard_index = index
            break

    if wildcard_index < 0:
        return candidate.parent, candidate.name

    root_parts = parts[:wildcard_index]
    if not root_parts:
        return None
    root = Path(root_parts[0])
    for part in root_parts[1:]:
        root /= part
    relative_pattern = "/".join(parts[wildcard_index:])
    return root, relative_pattern


def _looks_like_git_repo(path: Path) -> bool:
    """启发式判断：确定搜索时是否应该包含隐藏路径
    
    对于代码库，隐藏目录如 `.github/` 是相关的；
    对于任意目录（如用户主目录），搜索隐藏路径可能会爆炸搜索空间。
    
    Args:
        path: 要检查的路径
    
    Returns:
        bool: 是否像Git仓库
    """
    current = path
    for _ in range(6):
        git_dir = current / ".git"
        if git_dir.exists():
            return True
        if current.parent == current:
            break
        current = current.parent
    return False


async def _glob(root: Path, pattern: str, *, limit: int) -> list[str]:
    """快速glob实现
    
    使用ripgrep的文件遍历器（可用时），尊重.gitignore并可跳过重目录如`.venv/`，
    有Python后备方案。
    
    Args:
        root: 搜索根目录
        pattern: glob模式
        limit: 结果数量限制
    
    Returns:
        list[str]: 匹配的文件路径列表
    """
    # 检查ripgrep是否可用
    if not root.exists():
        return []

    rg = shutil.which("rg")
    # Path.glob("**/*") 会遍历隐藏和忽略的路径（如 .venv/）
    # 在实际工作区上可能很慢。优先使用 rg --files。
    if rg and ("**" in pattern or "/" in pattern):
        # 判断是否应该包含隐藏文件
        include_hidden = _looks_like_git_repo(root)
        cmd = [rg, "--files", "--no-messages"]
        if include_hidden:
            cmd.append("--hidden")
        cmd.extend(["--glob", pattern, "."])

        # 创建异步子进程执行ripgrep
        kwargs: dict = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(root),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            **kwargs,
        )

        lines: list[str] = []
        try:
            assert process.stdout is not None
            # 读取输出直到达到限制
            while len(lines) < limit:
                try:
                    raw = await process.stdout.readline()
                except asyncio.CancelledError:
                    process.kill()
                    raise
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    lines.append(line)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

        # 按修改时间降序排列
        def _mtime_key(line: str) -> float:
            return (root / line).stat().st_mtime
        lines.sort(key=_mtime_key, reverse=True)
        return lines

    # 后备：非递归模式通常很便宜；在线程中运行以避免阻塞事件循环
    def _fallback() -> list[str]:
        paths = list(root.glob(pattern))
        paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [str(p.relative_to(root)) for p in paths[:limit]]
    return await asyncio.to_thread(_fallback)
