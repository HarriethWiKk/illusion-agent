"""
最小 Jupyter notebook 编辑工具
==============================

本模块提供编辑 Jupyter notebook 单元格的功能，无需使用 nbformat。

主要组件：
    - NotebookEditTool: 编辑 notebook 单元格的工具

使用示例：
    >>> from illusion.tools import NotebookEditTool
    >>> tool = NotebookEditTool()
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from illusion.config.paths import resolve_relative_path
from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult
from illusion.utils.atomic_write import atomic_write_text
from illusion.utils.file_state_cache import FileState, FileStateCache


class NotebookEditToolInput(BaseModel):
    """Notebook 编辑参数。

    属性：
        notebook_path: Jupyter notebook 文件的绝对路径
        cell_id: 要编辑的单元格 ID
        new_source: 单元格的新源代码
        cell_type: 单元格类型（code 或 markdown）
        edit_mode: 编辑类型：replace、insert 或 delete
    """

    notebook_path: str = Field(description="The absolute path to the Jupyter notebook file")
    cell_id: str | None = Field(
        default=None,
        description="The ID of the cell to edit. Use edit_mode=insert to add a new cell at this index, edit_mode=delete to delete.",
    )
    new_source: str = Field(default="", description="The new source for the cell")
    cell_type: Literal["code", "markdown"] | None = Field(
        default=None,
        description="The type of the cell (code or markdown). Required for insert mode. Defaults to the current cell type for replace.",
    )
    edit_mode: Literal["replace", "insert", "delete"] = Field(
        default="replace",
        description="The type of edit to make. replace: replace cell content, insert: add new cell at index, delete: remove the cell.",
    )


class NotebookEditTool(BaseTool[NotebookEditToolInput]):
    """编辑 notebook 单元格而不需要 nbformat。

    用于修改 Jupyter notebook (.ipynb 文件) 中的单元格内容。
    """

    name = "notebook_edit"
    description = """Completely replaces the contents of a specific cell in a Jupyter notebook (.ipynb file) with new source. Jupyter notebooks are interactive documents that combine code, text, and visualizations, commonly used for data analysis and scientific computing. The notebook_path parameter must be an absolute path, not a relative path. The cell_id is 0-indexed. Use edit_mode=insert to add a new cell at the index specified by cell_id. Use edit_mode=delete to delete the cell at the index specified by cell_id. Defaults to edit_mode=replace. When using edit_mode=insert, cell_type is required. When using edit_mode=replace, cell_type defaults to the current cell type."""
    input_model = NotebookEditToolInput

    async def execute(
        self,
        arguments: NotebookEditToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        # 解析文件路径
        try:
            path = resolve_relative_path(context.cwd, arguments.notebook_path)
        except ValueError as exc:
            return ToolResult(output=str(exc), is_error=True)

        # 验证 .ipynb 扩展名
        if path.suffix.lower() != ".ipynb":
            return ToolResult(
                output=f"File must have .ipynb extension: {path}",
                is_error=True,
            )

        # 获取文件状态缓存
        cache: FileStateCache | None = context.metadata.get("file_state_cache")

        # 对现有文件进行读后编辑检查（基于缓存）
        abs_path = str(path)
        if await asyncio.to_thread(path.exists) and cache is not None:
            cached = cache.get(abs_path)
            if cached is None:
                return ToolResult(
                    output=f"You must read the file at {path} using the Read tool before you can edit it.",
                    is_error=True,
                )

            # mtime 过期检测
            try:
                current_mtime = await asyncio.to_thread(os.path.getmtime, path)
                if current_mtime > cached.timestamp:
                    return ToolResult(
                        output=f"File {path} has been modified since last read. Please read it again before editing.",
                        is_error=True,
                    )
            except OSError:
                pass

        # 加载 notebook
        notebook = await asyncio.to_thread(_load_notebook, path)
        if notebook is None:
            return ToolResult(output=f"Notebook not found: {path}", is_error=True)

        # 获取单元格列表
        cells = notebook.setdefault("cells", [])

        # 从 cell_id 解析单元格索引
        cell_index = _resolve_cell_index(cells, arguments.cell_id)
        if cell_index is None:
            return ToolResult(
                output=f"Cell ID '{arguments.cell_id}' not found in notebook {path}",
                is_error=True,
            )

        # 确定单元格类型
        effective_cell_type = arguments.cell_type
        if effective_cell_type is None:
            if arguments.edit_mode == "insert":
                return ToolResult(
                    output="cell_type is required for insert mode",
                    is_error=True,
                )
            # 对于 replace/delete，使用现有单元格类型
            if 0 <= cell_index < len(cells):
                effective_cell_type = cells[cell_index].get("cell_type", "code")
            else:
                effective_cell_type = "code"

        # 执行编辑操作
        if arguments.edit_mode == "delete":
            if cell_index >= len(cells):
                return ToolResult(
                    output=f"Cell index {cell_index} out of range (notebook has {len(cells)} cells)",
                    is_error=True,
                )
            cells.pop(cell_index)
            await asyncio.to_thread(_save_notebook, path, notebook)
            # 更新缓存
            await asyncio.to_thread(_update_cache, cache, abs_path, path, notebook)
            return ToolResult(
                output=f"Deleted cell {cell_index} from {path}"
            )

        if arguments.edit_mode == "insert":
            new_cell = _empty_cell(effective_cell_type)
            new_cell["id"] = _generate_cell_id()
            new_cell["source"] = arguments.new_source
            # 在指定索引处插入
            insert_at = min(cell_index, len(cells))
            cells.insert(insert_at, new_cell)
            await asyncio.to_thread(_save_notebook, path, notebook)
            # 更新缓存
            await asyncio.to_thread(_update_cache, cache, abs_path, path, notebook)
            return ToolResult(
                output=f"Inserted cell at index {insert_at} in {path}"
            )

        # Replace 模式
        if cell_index >= len(cells):
            return ToolResult(
                output=f"Cell index {cell_index} out of range (notebook has {len(cells)} cells)",
                is_error=True,
            )

        cell = cells[cell_index]
        cell["cell_type"] = effective_cell_type
        cell.setdefault("metadata", {})
        if effective_cell_type == "code":
            cell.setdefault("outputs", [])
            cell.setdefault("execution_count", None)
            # 替换时重置执行状态
            cell["execution_count"] = None
            cell["outputs"] = []

        cell["source"] = arguments.new_source

        await asyncio.to_thread(_save_notebook, path, notebook)
        # 更新缓存
        await asyncio.to_thread(_update_cache, cache, abs_path, path, notebook)
        return ToolResult(output=f"Updated notebook cell {cell_index} in {path}")


def _resolve_cell_index(cells: list[dict[str, Any]], cell_id: str | None) -> int | None:
    """将 cell_id 解析为数字索引。

    支持：
    - None → 默认为 0
    - 数字索引如 "3" → 3
    - "cell-N" 格式 → N
    - 实际单元格 ID 字符串 → 按 id 字段匹配
    """
    if cell_id is None:
        return 0

    # 尝试直接解析为数字索引
    try:
        return int(cell_id)
    except ValueError:
        pass

    # 尝试 "cell-N" 格式
    if cell_id.startswith("cell-"):
        try:
            return int(cell_id[5:])
        except ValueError:
            pass

    # 尝试匹配实际单元格 ID
    for i, cell in enumerate(cells):
        if cell.get("id") == cell_id:
            return i

    return None


def _load_notebook(path: Path) -> dict[str, Any] | None:
    """从磁盘加载 notebook。如果文件不存在返回 None。"""
    if not path.exists():
        return None
    result: dict[str, Any] | None = json.loads(path.read_text(encoding="utf-8"))
    return result


def _save_notebook(path: Path, notebook: dict[str, Any]) -> None:
    """将 notebook 保存到磁盘。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(notebook, indent=1) + "\n")


def _update_cache(
    cache: FileStateCache | None,
    abs_path: str,
    path: Path,
    notebook: dict[str, Any],
) -> None:
    """更新文件状态缓存。

    Args:
        cache: 文件状态缓存（可选）
        abs_path: 绝对路径
        path: Path 对象
        notebook: notebook 内容
    """
    if cache is None:
        return
    try:
        mtime = os.path.getmtime(path)
        content = json.dumps(notebook, indent=1) + "\n"
        cache.set(abs_path, FileState(
            content=content,
            timestamp=mtime,
            offset=None,  # 标记为非 Read 来源
            limit=None,
        ))
    except OSError:
        pass  # 无法获取 mtime，跳过缓存


def _generate_cell_id() -> str:
    """为 nbformat >= 4.5 生成唯一的单元格 ID。"""
    return secrets.token_hex(8)


def _empty_cell(cell_type: str) -> dict[str, Any]:
    """创建空单元格。"""
    if cell_type == "markdown":
        return {"cell_type": "markdown", "metadata": {}, "source": ""}
    return {
        "cell_type": "code",
        "metadata": {},
        "source": "",
        "outputs": [],
        "execution_count": None,
    }


def _normalize_source(source: str | list[str]) -> str:
    """规范化源代码（支持字符串或字符串列表）。"""
    if isinstance(source, list):
        return "".join(source)
    return str(source)
