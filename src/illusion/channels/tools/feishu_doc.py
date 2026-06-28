"""飞书文档工具
==============

提供 agent 可调用的飞书文档读取/创建/写入/删除工具。

工具自行从渠道配置构造 lark 客户端，不依赖评论事件注入
（与 hermes 的 thread-local client 模式不同）。

工具说明：
    - FeishuDocReadTool: 读取 Docx/Wiki 原文（raw 纯文本或 blocks 结构化 JSON）
    - FeishuDocCreateTool: 创建新 Docx 文档并返回 token/URL
    - FeishuDocWriteTool: 向已有文档追加 text/code/heading block
    - FeishuDocDeleteTool: 删除文档到回收站
"""
from __future__ import annotations

import json  # blocks 格式序列化
from typing import TYPE_CHECKING, Any  # 类型

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
        format: 返回格式，raw（纯文本）或 blocks（结构化 JSON）
    """

    doc_token: str = Field(..., description="Document token (from URL or context)")
    doc_type: str = Field("docx", description="Document type: docx or wiki")
    format: str = Field("raw", description="Return format: raw (plain text) or blocks (structured JSON)")


class FeishuDocReadTool(BaseTool[FeishuDocReadInput]):
    """读取飞书文档全文

    format="raw" 时调用 docx/v1/documents/:id/raw_content 接口获取文档纯文本。
    format="blocks" 时调用 docx/v1/documents/:id/blocks 获取结构化 block 列表（JSON）。
    """

    name = "feishu_doc_read"
    description = "Read the full content of a Feishu/Lark document as plain text or structured blocks."
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

        if arguments.format == "blocks":
            try:
                from lark_oapi.api.docx.v1 import (  # type: ignore[import-untyped]
                    ListDocumentBlockRequest,
                )
            except ImportError:
                return ToolResult(output="lark_oapi docx API not available", is_error=True)
            req = (
                ListDocumentBlockRequest.builder()
                .document_id(arguments.doc_token)
                .page_size(500)
                .build()
            )
            resp = client.docx.v1.document_block.list(req)
            if not resp.success():
                return ToolResult(
                    output=f"Failed to list blocks: code={resp.code} msg={resp.msg}",
                    is_error=True,
                )
            data = getattr(resp, "data", None)
            items = getattr(data, "items", []) if data else []
            return ToolResult(
                output=json.dumps(
                    [self._block_to_dict(b) for b in items],
                    ensure_ascii=False,
                    indent=2,
                )
            )

        # raw 格式（现有逻辑）
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

    @staticmethod
    def _block_to_dict(block: Any) -> dict:
        """将 block 对象转为 dict（简化版）

        Args:
            block: lark-oapi Block 对象

        Returns:
            dict: 包含 block_type 与已知子字段（text/code/headingN）的字典
        """
        result: dict[str, Any] = {"block_type": getattr(block, "block_type", None)}
        for attr in ["text", "code", "heading1", "heading2", "heading3"]:
            val = getattr(block, attr, None)
            if val is not None:
                result[attr] = str(val)
        return result


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
            ToolResult: 创建结果（含 doc_token 与 url）或错误
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
        req = CreateDocumentRequest.builder().request_body(body).build()  # pyright: ignore[reportArgumentType]
        resp = client.docx.v1.document.create(req)
        if not resp.success():
            return ToolResult(
                output=f"Failed to create document: code={resp.code} msg={resp.msg}",
                is_error=True,
            )
        data = getattr(resp, "data", None)
        doc = getattr(data, "document", None) if data else None
        token = getattr(doc, "document_id", "") if doc else ""
        # 拼接文档 URL：feishu 域用 feishu.cn，其余（lark）用 larksuite.com
        domain = self._cfg.domain or "feishu"
        host = "feishu.cn" if domain == "feishu" else "larksuite.com"
        url = f"https://{host}/docx/{token}" if token else ""
        return ToolResult(output=f"Created document: token={token} url={url}")


class FeishuDocWriteInput(BaseModel):
    """飞书文档写入工具输入

    Attributes:
        doc_token: 文档 token
        content: 要写入的内容
        block_type: 块类型，text（文本）/ code（代码块）/ heading（标题）
    """

    doc_token: str = Field(..., description="Document token to write to")
    content: str = Field(..., description="Content to append")
    block_type: str = Field("text", description="Block type: text, code, or heading")


class FeishuDocWriteTool(BaseTool[FeishuDocWriteInput]):
    """向飞书文档追加内容

    通过 docx/v1/documents/:id/blocks/:id/children 接口追加 text/code/heading block。
    """

    name = "feishu_doc_write"
    description = "Append content (text/code/heading) to an existing Feishu/Lark document."
    input_model = FeishuDocWriteInput

    def __init__(self, channel_config: "FeishuChannelConfig") -> None:
        """初始化

        Args:
            channel_config: 飞书渠道配置
        """
        self._cfg = channel_config

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        """执行文档写入

        Args:
            arguments: 输入参数（FeishuDocWriteInput）
            context: 执行上下文

        Returns:
            ToolResult: 写入结果或错误
        """
        assert isinstance(arguments, FeishuDocWriteInput)
        client = build_lark_client(self._cfg)
        try:
            from lark_oapi.api.docx.v1 import (  # type: ignore[import-untyped]
                Block,
                CodeBlock,
                CreateDocumentBlockChildrenRequest,
                TextBlock,
            )
        except ImportError:
            return ToolResult(output="lark_oapi docx API not available", is_error=True)

        # 构造 block：text=2 / heading1=3 / code=14（lark-oapi block_type 常量）
        elements = [{"text_run": {"content": arguments.content}}]
        if arguments.block_type == "code":
            block = (
                Block.builder()
                .block_type(14)
                .code(CodeBlock.builder().elements(elements).style("{}").build())
                .build()
            )
        elif arguments.block_type == "heading":
            block = (
                Block.builder()
                .block_type(3)
                .heading1(TextBlock.builder().elements(elements).build())
                .build()
            )
        else:  # text
            block = (
                Block.builder()
                .block_type(2)
                .text(TextBlock.builder().elements(elements).build())
                .build()
            )

        # document_id 与 block_id 均传 doc_token：以文档根 block 作为父
        req = (
            CreateDocumentBlockChildrenRequest.builder()
            .document_id(arguments.doc_token)
            .block_id(arguments.doc_token)
            .request_body({"children": [block]})
            .build()
        )
        resp = client.docx.v1.document_block_children.create(req)
        if not resp.success():
            return ToolResult(
                output=f"Failed to write: code={resp.code} msg={resp.msg}",
                is_error=True,
            )
        return ToolResult(output=f"Written {arguments.block_type} block to {arguments.doc_token}")


class FeishuDocDeleteInput(BaseModel):
    """飞书文档删除工具输入

    Attributes:
        doc_token: 文档 token
    """

    doc_token: str = Field(..., description="Document token to delete")


class FeishuDocDeleteTool(BaseTool[FeishuDocDeleteInput]):
    """删除飞书文档到回收站

    通过 drive/v1/files/:token 接口（type=docx）将文档移至回收站。
    """

    name = "feishu_doc_delete"
    description = "Delete a Feishu/Lark document (move to trash)."
    input_model = FeishuDocDeleteInput

    def __init__(self, channel_config: "FeishuChannelConfig") -> None:
        """初始化

        Args:
            channel_config: 飞书渠道配置
        """
        self._cfg = channel_config

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        """执行文档删除

        Args:
            arguments: 输入参数（FeishuDocDeleteInput）
            context: 执行上下文

        Returns:
            ToolResult: 删除结果或错误
        """
        assert isinstance(arguments, FeishuDocDeleteInput)
        client = build_lark_client(self._cfg)
        try:
            from lark_oapi.api.drive.v1 import (  # type: ignore[import-untyped]
                DeleteFileRequest,
            )
        except ImportError:
            return ToolResult(output="lark_oapi drive API not available", is_error=True)

        req = DeleteFileRequest.builder().file_token(arguments.doc_token).type("docx").build()
        resp = client.drive.v1.file.delete(req)
        if not resp.success():
            return ToolResult(
                output=f"Failed to delete: code={resp.code} msg={resp.msg}",
                is_error=True,
            )
        return ToolResult(output=f"Deleted document: {arguments.doc_token}")
