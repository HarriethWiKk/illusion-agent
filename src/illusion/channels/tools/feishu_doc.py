"""飞书文档工具
==============

提供 agent 可调用的飞书文档读取/创建工具。

工具自行从渠道配置构造 lark 客户端，不依赖评论事件注入
（与 hermes 的 thread-local client 模式不同）。

工具说明：
    - FeishuDocReadTool: 读取 Docx/Wiki 原文为纯文本
    - FeishuDocCreateTool: 创建新 Docx 文档
"""
from __future__ import annotations

from typing import Any,  TYPE_CHECKING  # 类型

from pydantic import BaseModel, Field  # 数据模型

from illusion.channels.feishu.messaging import build_lark_client  # 客户端构造
from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult  # 工具基类

if TYPE_CHECKING:
    from illusion.channels.config import FeishuChannelConfig  # 配置


class FeishuDocReadInput(BaseModel):
    """飞书文档读取工具输入

    Attributes:
        doc_token: 文档 token（从 URL 或上下文获取）
        doc_type: 文档类型，docx 或 wiki
    """

    doc_token: str = Field(..., description="Document token (from URL or context)")
    doc_type: str = Field("docx", description="Document type: docx or wiki")


class FeishuDocReadTool(BaseTool[FeishuDocReadInput]):
    """读取飞书文档全文为纯文本

    调用 docx/v1/documents/:id/raw_content 接口获取文档原文。
    """

    name = "feishu_doc_read"
    description = "Read the full content of a Feishu/Lark document as plain text."
    input_model = FeishuDocReadInput

    def __init__(self, channel_config: "FeishuChannelConfig") -> None:
        """初始化

        Args:
            channel_config: 飞书渠道配置（提供凭据）
        """
        self._cfg = channel_config  # 渠道配置

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        """执行文档读取

        Args:
            arguments: 输入参数（FeishuDocReadInput）
            context: 执行上下文

        Returns:
            ToolResult: 文档内容或错误
        """
        assert isinstance(arguments, FeishuDocReadInput)
        client = build_lark_client(self._cfg)
        try:
            from lark_oapi.api.docx.v1 import (  # type: ignore[import-untyped]
                RawContentDocumentRequest,
            )
        except ImportError:
            return ToolResult(output="lark_oapi docx API not available", is_error=True)

        # lark-oapi 使用 builder 模式构造请求
        req = RawContentDocumentRequest.builder().document_id(arguments.doc_token).build()
        resp = client.docx.v1.document.raw_content(req)
        if not resp.success():
            return ToolResult(
                output=f"Failed to read document: code={resp.code} msg={resp.msg}",
                is_error=True,
            )
        # 解析返回内容：response.data.content 为文档纯文本
        raw = getattr(resp, "data", None)
        if raw and hasattr(raw, "content"):
            return ToolResult(output=str(raw.content))
        return ToolResult(output=str(raw or "(empty document)"))


class FeishuDocCreateInput(BaseModel):
    """飞书文档创建工具输入

    Attributes:
        title: 文档标题
        folder_token: 父文件夹 token（可选，默认根目录）
    """

    title: str = Field(..., description="Document title")
    folder_token: str = Field("", description="Parent folder token (optional)")


class FeishuDocCreateTool(BaseTool[FeishuDocCreateInput]):
    """创建新飞书 Docx 文档"""

    name = "feishu_doc_create"
    description = "Create a new Feishu/Lark Docx document and return its token/URL."
    input_model = FeishuDocCreateInput

    def __init__(self, channel_config: "FeishuChannelConfig") -> None:
        """初始化

        Args:
            channel_config: 飞书渠道配置
        """
        self._cfg = channel_config

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        """执行文档创建

        Args:
            arguments: 输入参数（FeishuDocCreateInput）
            context: 执行上下文

        Returns:
            ToolResult: 创建结果（含 doc_token）或错误
        """
        assert isinstance(arguments, FeishuDocCreateInput)
        client = build_lark_client(self._cfg)
        try:
            from lark_oapi.api.docx.v1 import (
                CreateDocumentRequest,
            )
        except ImportError:
            return ToolResult(output="lark_oapi docx API not available", is_error=True)

        # lark-oapi 用 builder + dict[str, Any] 构造请求（RequestBody 类不接受关键字参数）
        body = {"folder_token": arguments.folder_token, "title": arguments.title}
        req = CreateDocumentRequest.builder().request_body(body).build()
        resp = client.docx.v1.document.create(req)
        if not resp.success():
            return ToolResult(
                output=f"Failed to create document: code={resp.code} msg={resp.msg}",
                is_error=True,
            )
        data = getattr(resp, "data", None)
        doc = getattr(data, "document", None) if data else None
        token = getattr(doc, "document_id", "") if doc else ""
        return ToolResult(output=f"Created document: token={token}")
