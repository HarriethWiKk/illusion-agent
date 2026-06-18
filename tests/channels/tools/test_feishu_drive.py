"""飞书云盘工具测试（mock SDK）。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from illusion.channels.config import FeishuChannelConfig
from illusion.channels.tools.feishu_drive import (
    FeishuDriveListInput,
    FeishuDriveListTool,
)
from illusion.tools.base import ToolExecutionContext


def _cfg():
    """构造飞书配置。"""
    return FeishuChannelConfig(enabled=True, app_id="cli", app_secret="s")


@pytest.mark.asyncio
async def test_drive_list_returns_files():
    """成功列出云盘文件。"""
    tool = FeishuDriveListTool(_cfg())
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.success.return_value = True
    fake_file = MagicMock()
    fake_file.name = "report.docx"
    fake_file.file_token = "boxcn1"
    fake_file.type = "docx"
    fake_resp.data = MagicMock(files=[fake_file])
    fake_client.drive.v1.file.list.return_value = fake_resp

    with patch("illusion.channels.tools.feishu_drive.build_lark_client", return_value=fake_client):
        result = await tool.execute(
            FeishuDriveListInput(),
            ToolExecutionContext(cwd=Path(".")),
        )
    assert result.is_error is False
    assert "report.docx" in result.output


@pytest.mark.asyncio
async def test_drive_list_handles_error():
    """API 错误返回错误结果。"""
    tool = FeishuDriveListTool(_cfg())
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.success.return_value = False  # API 失败
    fake_resp.code = 99991663
    fake_resp.msg = "invalid folder"
    fake_resp.data = None
    fake_client.drive.v1.file.list.return_value = fake_resp

    with patch("illusion.channels.tools.feishu_drive.build_lark_client", return_value=fake_client):
        result = await tool.execute(
            FeishuDriveListInput(),
            ToolExecutionContext(cwd=Path(".")),
        )
    assert result.is_error is True
