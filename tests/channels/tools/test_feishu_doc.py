"""飞书文档工具测试（mock SDK）。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("lark_oapi")

from illusion.channels.config import FeishuChannelConfig
from illusion.channels.tools.feishu_doc import FeishuDocReadInput, FeishuDocReadTool
from illusion.tools.base import ToolExecutionContext


def _cfg():
    """构造飞书配置。"""
    return FeishuChannelConfig(enabled=True, app_id="cli", app_secret="s")


@pytest.mark.asyncio
async def test_doc_read_returns_content():
    """成功读取文档返回内容。"""
    tool = FeishuDocReadTool(_cfg())
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.success.return_value = True
    fake_data = MagicMock()
    fake_data.content = "hello world"
    fake_resp.data = fake_data
    fake_client.docx.v1.document.raw_content.return_value = fake_resp

    with patch("illusion.channels.tools.feishu_doc.build_lark_client", return_value=fake_client):
        result = await tool.execute(
            FeishuDocReadInput(doc_token="doccn123"),
            ToolExecutionContext(cwd=Path(".")),
        )
    assert result.is_error is False
    assert "hello world" in result.output


@pytest.mark.asyncio
async def test_doc_read_handles_api_error():
    """API 返回错误码时返回错误结果。"""
    tool = FeishuDocReadTool(_cfg())
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.success.return_value = False  # API 失败
    fake_resp.code = 99991668
    fake_resp.msg = "permission denied"
    fake_resp.data = None
    fake_client.docx.v1.document.raw_content.return_value = fake_resp

    with patch("illusion.channels.tools.feishu_doc.build_lark_client", return_value=fake_client):
        result = await tool.execute(
            FeishuDocReadInput(doc_token="doccn123"),
            ToolExecutionContext(cwd=Path(".")),
        )
    assert result.is_error is True
    assert "99991668" in result.output or "permission" in result.output.lower()
