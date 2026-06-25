"""Tests for web fetch and search tools."""

from __future__ import annotations

import contextlib
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from urllib.parse import parse_qs, urlparse

from illusion.tools.base import ToolExecutionContext
from illusion.tools.web_fetch_tool import WebFetchTool, WebFetchToolInput
from illusion.tools.web_search_tool import WebSearchTool, WebSearchToolInput


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        query = parse_qs(urlparse(self.path).query).get("q", [""])[0]
        if query:
            body = (
                "<html><body>"
                '<a class="result__a" href="https://example.com/docs">IllusionCode Docs</a>'
                '<div class="result__snippet">Search query was %s and docs were found.</div>'
                "</body></html>"
            ) % query
        else:
            body = "<html><body><h1>IllusionCode Test</h1><p>web fetch works</p></body></html>"
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        del format, args


def _make_mock_response(html: str) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_resp.text = html
    mock_resp.is_redirect = False
    mock_resp.raise_for_status = MagicMock()
    mock_resp.url = "https://example.com/"
    return mock_resp


@pytest.mark.asyncio
async def test_web_fetch_tool_reads_html(tmp_path):
    from illusion.tools import web_fetch_tool
    # 清理会话级缓存（ContextVar 懒初始化，需先 set 再 clear）
    try:
        web_fetch_tool._get_cache().clear()
    except LookupError:
        pass

    mock_resp = _make_mock_response(
        "<html><body><h1>IllusionCode Test</h1><p>web fetch works</p></body></html>"
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("illusion.tools.web_fetch_tool.httpx.AsyncClient", return_value=mock_client):
        tool = WebFetchTool()
        result = await tool.execute(
            WebFetchToolInput(url="https://example.com/"),
            ToolExecutionContext(cwd=tmp_path),
        )

    assert result.is_error is False
    assert "IllusionCode Test" in result.output
    assert "web fetch works" in result.output


@pytest.mark.asyncio
async def test_web_search_tool_reads_results(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        tool = WebSearchTool()
        result = await tool.execute(
            WebSearchToolInput(
                query="illusion docs",
                search_url=f"http://127.0.0.1:{server.server_port}/search",
            ),
            ToolExecutionContext(cwd=tmp_path),
        )
    finally:
        server.shutdown()
        with contextlib.suppress(Exception):
            server.server_close()
        thread.join(timeout=1)

    assert result.is_error is False
    assert "IllusionCode Docs" in result.output
    assert "https://example.com/docs" in result.output
    assert "illusion docs" in result.output
