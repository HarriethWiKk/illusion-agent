"""
记忆路径模块
==========

本模块提供持久化项目记忆的路径管理功能。

主要功能：
    - 生成基于项目路径的唯一记忆目录
    - 管理MEMORY.md入口点文件
    - 支持项目级记忆目录（.illusion/memory/）

函数说明：
    - get_memory_dir: 获取全局 memory 根目录（~/.illusion/memory）
    - get_project_memory_dir: 获取项目记忆目录（全局配置目录）
    - get_project_local_memory_dir: 获取项目级记忆目录（.illusion/memory/）
    - get_memory_entrypoint: 获取记忆入口点文件

使用示例：
    >>> from illusion.memory import get_project_memory_dir, get_memory_entrypoint
    >>> mem_dir = get_project_memory_dir(".")
    >>> entrypoint = get_memory_entrypoint(".")
"""

from __future__ import annotations

from hashlib import sha1
from pathlib import Path

from illusion.config.paths import get_config_dir


def get_memory_dir() -> Path:
    """返回全局 memory 根目录（~/.illusion/memory）。

    与项目级目录 {cwd}/.illusion/memory/ 对称。
    """
    return get_config_dir() / "memory"


def get_project_memory_dir(cwd: str | Path) -> Path:
    """获取项目持久化记忆目录（全局配置目录）

    目录名格式: {项目名}-{sha1哈希前12位}
    使用项目路径的哈希确保唯一性。
    路径位于 ~/.illusion/memory/，与项目级 {cwd}/.illusion/memory/ 对称。

    Args:
        cwd: 当前工作目录

    Returns:
        Path: 记忆目录的Path对象
    """
    path = Path(cwd).resolve()
    digest = sha1(str(path).encode("utf-8")).hexdigest()[:12]
    memory_dir = get_memory_dir() / f"{path.name}-{digest}"
    memory_dir.mkdir(parents=True, exist_ok=True)
    return memory_dir


def get_project_local_memory_dir(cwd: str | Path) -> Path:
    """获取项目级记忆目录（.illusion/memory/）

    项目级记忆目录位于项目根目录下的 .illusion/memory/，
    用于存储项目特定的记忆配置。

    Args:
        cwd: 当前工作目录

    Returns:
        Path: 项目级记忆目录的Path对象
    """
    project_dir = Path(cwd).resolve() / ".illusion" / "memory"  # 构建项目级记忆目录路径
    project_dir.mkdir(parents=True, exist_ok=True)  # 创建目录
    return project_dir  # 返回目录


def get_memory_entrypoint(cwd: str | Path) -> Path:
    """获取项目记忆入口点文件

    优先返回项目级记忆目录下的 MEMORY.md，
    如果不存在则返回全局记忆目录下的 MEMORY.md。

    Args:
        cwd: 当前工作目录

    Returns:
        Path: MEMORY.md文件的Path对象
    """
    # 优先使用项目级记忆目录
    local_entrypoint = get_project_local_memory_dir(cwd) / "MEMORY.md"
    if local_entrypoint.exists():
        return local_entrypoint

    # 回退到全局记忆目录
    return get_project_memory_dir(cwd) / "MEMORY.md"