"""
工具搜索工具
============

本模块提供搜索可用工具注册表的功能，支持精确名称查询和关键词搜索，
返回匹配工具的完整 JSONSchema 定义。

主要组件：
    - ToolSearchTool: 搜索工具注册表的工具

使用示例：
    >>> from illusion.tools import ToolSearchTool
    >>> tool = ToolSearchTool()
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult


class ToolSearchToolInput(BaseModel):
    """工具搜索参数。

    属性：
        query: 在工具名称和描述中搜索的子字符串，支持特殊查询语法：
            - "select:Tool1,Tool2" — 按名称精确获取
            - "+term other" — 要求名称包含 term，按剩余词排序
            - "keyword list" — 关键词搜索，按匹配度排序
    """

    query: str = Field(description="Substring to search in tool names and descriptions")


class ToolSearchTool(BaseTool[ToolSearchToolInput]):
    """搜索工具注册表内容并返回匹配工具的完整 schema 定义。

    支持三种查询模式：
    1. select: 前缀 — 按逗号分隔的名称精确匹配
    2. + 前缀 — 要求第一个词出现在工具名称中，按剩余词排名
    3. 普通关键词 — 按匹配度排序返回最佳结果
    """

    name = "tool_search"
    description = """Fetches full schema definitions for deferred tools so they can be called.

Deferred tools appear by name in <system-reminder> messages. Until fetched, only the name is known — there is no parameter schema, so the tool cannot be invoked. This tool takes a query, matches it against the deferred tool list, and returns the matched tools' complete JSONSchema definitions inside a <functions> block. Once a tool's schema appears in that result, it is callable exactly like any tool defined at the top of this prompt.

Result format: each matched tool appears as one <function>{"description": "...", "name": "...", "parameters": {...}}</function> line inside the <functions> block — the same encoding as the tool list at the top of this prompt.

Query forms:
- "select:Read,Edit,Grep" — fetch these exact tools by name
- "notebook jupyter" — keyword search, up to max_results best matches
- "+slack send" — require "slack" in the name, rank by remaining terms"""
    input_model = ToolSearchToolInput

    def is_read_only(self, arguments: ToolSearchToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: ToolSearchToolInput, context: ToolExecutionContext) -> ToolResult:
        registry = context.metadata.get("tool_registry") if hasattr(context, "metadata") else None
        if registry is None:
            return ToolResult(output="Tool registry context not available", is_error=True)

        query = arguments.query.strip()
        all_tools = registry.list_tools()

        matches = self._match_tools(query, all_tools)

        if not matches:
            return ToolResult(output="(no matches)")

        functions_xml = self._build_functions_block(matches)
        return ToolResult(output=functions_xml)

    def _match_tools(self, query: str, all_tools: list[BaseTool[Any]]) -> list[BaseTool[Any]]:
        """根据查询语法匹配工具。

        Args:
            query: 查询字符串
            all_tools: 所有已注册工具

        Returns:
            匹配的工具列表
        """
        if query.startswith("select:"):
            return self._match_select(query, all_tools)
        if query.startswith("+"):
            return self._match_require(query, all_tools)
        return self._match_keyword(query, all_tools)

    def _match_select(self, query: str, all_tools: list[BaseTool[Any]]) -> list[BaseTool[Any]]:
        """select:Name1,Name2,... — 按名称精确匹配。"""
        names = {n.strip() for n in query[len("select:"):].split(",") if n.strip()}
        return [t for t in all_tools if t.name in names]

    def _match_require(self, query: str, all_tools: list[BaseTool[Any]]) -> list[BaseTool[Any]]:
        """+term other... — 名称必须包含 term，按剩余词排名，最多返回 5 个。"""
        parts = query.split()
        if not parts:
            return []
        required = parts[0][1:]  # 去掉前导 +
        remaining_terms = parts[1:]

        candidates = [t for t in all_tools if required.lower() in t.name.lower()]
        if not remaining_terms:
            return candidates[:5]

        scored = sorted(
            candidates,
            key=lambda t: self._keyword_score(t, remaining_terms),
            reverse=True,
        )
        return scored[:5]

    def _match_keyword(self, query: str, all_tools: list[BaseTool[Any]]) -> list[BaseTool[Any]]:
        """关键词搜索，按匹配度排序，最多返回 5 个。"""
        terms = query.lower().split()
        if not terms:
            return []

        scored = sorted(
            all_tools,
            key=lambda t: self._keyword_score(t, terms),
            reverse=True,
        )
        return [t for t in scored if self._keyword_score(t, terms) > 0][:5]

    @staticmethod
    def _keyword_score(tool: BaseTool[Any], terms: list[str]) -> int:
        """计算工具对关键词列表的匹配得分。"""
        text = (tool.name + " " + tool.description).lower()
        return sum(1 for term in terms if term in text)

    def _build_functions_block(self, tools: list[BaseTool[Any]]) -> str:
        """将工具列表构建为 <function>JSONSchema</function> 格式。"""
        lines: list[str] = []
        for tool in tools:
            schema_dict = self._tool_to_function_schema(tool)
            lines.append(f"<function>{json.dumps(schema_dict, ensure_ascii=False)}</function>")
        return "\n".join(lines)

    @staticmethod
    def _tool_to_function_schema(tool: BaseTool[Any]) -> dict[str, Any]:
        """将工具转换为 function schema 格式（使用 parameters 键）。"""
        api_schema = tool.to_api_schema()
        return {
            "name": api_schema["name"],
            "description": api_schema["description"],
            "parameters": api_schema["input_schema"],
        }
