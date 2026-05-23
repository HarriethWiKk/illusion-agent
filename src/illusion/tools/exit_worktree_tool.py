"""
退出工作树工具
=============

本模块提供移除 git 工作树的功能，用于结束工作树会话。

主要组件：
    - ExitWorktreeTool: 退出并可选删除工作树的工具

使用示例：
    >>> from illusion.tools import ExitWorktreeTool
    >>> tool = ExitWorktreeTool()
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult


class ExitWorktreeToolInput(BaseModel):
    """工作树移除参数。

    属性：
        action: 操作类型，keep 或 remove
        discard_changes: 是否放弃未提交的更改
    """

    action: Literal["keep", "remove"] = Field(
        description='"keep" leaves the worktree directory and branch intact on disk; "remove" deletes both.',
    )
    discard_changes: bool = Field(
        default=False,
        description='Only meaningful with action "remove". If true, force-remove even with uncommitted changes.',
    )


class ExitWorktreeTool(BaseTool):
    """移除 git 工作树。

    退出由 EnterWorktree 创建的工作树会话，并将会话返回到原始工作目录。
    """

    name = "exit_worktree"
    description = """Exit a worktree session created by EnterWorktree and return the session to the original working directory.

## Scope

This tool ONLY operates on worktrees created by EnterWorktree in this session. It will NOT touch:
- Worktrees you created manually with `git worktree add`
- Worktrees from a previous session (even if created by EnterWorktree then)
- The directory you're in if EnterWorktree was never called

If called outside an EnterWorktree session, the tool is a **no-op**: it reports that no worktree session is active and takes no action. Filesystem state is unchanged.

## When to Use

- The user explicitly asks to "exit the worktree", "leave the worktree", "go back", or otherwise end the worktree session
- Do NOT call this proactively — only when the user asks

## Parameters

- `action` (required): `"keep"` or `"remove"`
  - `"keep"` — leave the worktree directory and branch intact on disk. Use this if the user wants to come back to the work later, or if there are changes to preserve.
  - `"remove"` — delete the worktree directory and its branch. Use this for a clean exit when the work is done or abandoned.
- `discard_changes` (optional, default false): only meaningful with `action: "remove"`. If the worktree has uncommitted files or commits not on the original branch, the tool will REFUSE to remove it unless this is set to `true`. If the tool returns an error listing changes, confirm with the user before re-invoking with `discard_changes: true`.

## Behavior

- Restores the session's working directory to where it was before EnterWorktree
- Clears CWD-dependent caches (system prompt sections, memory files, plans directory) so the session state reflects the original directory
- If a tmux session was attached to the worktree: killed on `remove`, left running on `keep` (its name is returned so the user can reattach)
- Once exited, EnterWorktree can be called again to create a fresh worktree"""
    input_model = ExitWorktreeToolInput

    async def execute(
        self,
        arguments: ExitWorktreeToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        run_kwargs: dict = {}
        if sys.platform == "win32":
            run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        # 获取主仓库的公共 .git 目录（worktree 内也能正确指向主仓库）
        common_dir = _git_output(context.cwd, "rev-parse", "--git-common-dir")
        if common_dir is None:
            return ToolResult(output="Not in a git repository", is_error=True)

        # 解析主仓库根目录
        git_dir = Path(common_dir)
        if not git_dir.is_absolute():
            git_dir = (context.cwd / git_dir).resolve()
        else:
            git_dir = git_dir.resolve()
        main_repo_root = git_dir.parent

        # 检查当前 CWD 是否在 .illusion/worktrees/ 下
        worktree_base = (main_repo_root / ".illusion" / "worktrees").resolve()
        current_cwd = context.cwd.resolve()

        if not _is_subpath(current_cwd, worktree_base) and current_cwd != worktree_base:
            # 不在 worktree 中 — no-op（非错误）
            return ToolResult(output="No active worktree session found")

        worktree_path = current_cwd

        # keep 操作 — 保留工作树，仅恢复 CWD
        if arguments.action == "keep":
            return ToolResult(
                output=f"Worktree kept at {worktree_path}",
                metadata={"new_cwd": str(main_repo_root)},
            )

        # remove 操作
        # 获取分支名（在删除 worktree 之前）
        branch = _git_output(worktree_path, "rev-parse", "--abbrev-ref", "HEAD")

        # 检查未提交的更改，除非 discard_changes 为 true
        if not arguments.discard_changes:
            status_check = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
                **run_kwargs,
            )
            if status_check.stdout.strip():
                return ToolResult(
                    output=(
                        f"Worktree has uncommitted changes. "
                        f"Set discard_changes=true to force remove.\n"
                        f"Changes:\n{status_check.stdout.strip()[:500]}"
                    ),
                    is_error=True,
                )

        # 移除工作树
        cmd = ["git", "worktree", "remove"]
        if arguments.discard_changes:
            cmd.append("--force")
        cmd.append(str(worktree_path))

        result = subprocess.run(
            cmd,
            cwd=main_repo_root,
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
            **run_kwargs,
        )
        if result.returncode != 0:
            output = (result.stdout or result.stderr).strip() or f"Failed to remove worktree {worktree_path}"
            return ToolResult(output=output, is_error=True)

        # 删除对应的分支
        if branch and branch != "HEAD":
            subprocess.run(
                ["git", "branch", "-D", branch],
                cwd=main_repo_root,
                capture_output=True,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
                **run_kwargs,
            )

        output = (result.stdout or "").strip() or f"Removed worktree {worktree_path}"
        return ToolResult(
            output=output,
            metadata={"new_cwd": str(main_repo_root)},
        )


def _git_output(cwd: Path, *args: str) -> str | None:
    """执行 git 命令并返回输出。

    参数：
        cwd: 工作目录
        *args: git 命令参数

    返回：
        命令输出字符串，失败返回 None
    """
    run_kwargs: dict = {}
    if sys.platform == "win32":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
        **run_kwargs,
    )
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip()


def _is_subpath(path: Path, parent: Path) -> bool:
    """检查 path 是否为 parent 的子路径。

    参数：
        path: 要检查的路径
        parent: 父路径

    返回：
        是否为子路径
    """
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
