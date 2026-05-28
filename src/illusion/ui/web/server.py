"""
Web 服务器模块
=============

本模块提供 FastAPI 应用和 WebSocket 端点，用于启动 Web 前端服务。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from illusion.ui.web.ws_host import WebBackendHost, WebHostConfig

log = logging.getLogger(__name__)


def _find_frontend_dist() -> Path | None:
    """查找前端打包产物目录。"""
    candidates = [
        Path(__file__).parent.parent.parent.parent / "frontend" / "web" / "dist",
        Path(__file__).parent / "_web_dist",
    ]
    for p in candidates:
        if p.is_dir() and (p / "index.html").exists():
            return p
    return None


def create_app(
    *,
    dev: bool = False,
    host_config: WebHostConfig | None = None,
) -> FastAPI:
    """创建 FastAPI 应用实例。"""
    app = FastAPI(title="Illusion Code Web")

    if dev:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        config = host_config or WebHostConfig()
        host = WebBackendHost(config, websocket)
        try:
            await host.run()
        except WebSocketDisconnect:
            log.info("WebSocket client disconnected")
        except Exception:
            log.exception("WebSocket error")

    if not dev:
        dist_dir = _find_frontend_dist()
        if dist_dir is not None:
            app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="static")

    return app
