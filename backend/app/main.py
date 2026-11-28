"""The FastAPI application — the "front desk" that receives questions over HTTP.

Run:  uvicorn app.main:app --reload     (from backend/)
Docs: http://localhost:8000/docs        (interactive API explorer, free with FastAPI)
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import catalog_routes, chat, health, ops_routes
from app.config import get_settings
from app.terminology.server import mcp as terminology_mcp

log = logging.getLogger(__name__)

KEEP_ALIVE_INTERVAL = 600  # 10 minutes — well under Render's 15-min sleep threshold


async def _keep_alive(url: str) -> None:
    """Ping our own public URL to prevent Render from spinning the service down."""
    async with httpx.AsyncClient() as client:
        while True:
            await asyncio.sleep(KEEP_ALIVE_INTERVAL)
            try:
                await client.get(f"{url}/health", timeout=10)
            except Exception:  # noqa: BLE001
                pass


def create_app(with_pipeline: bool = True) -> FastAPI:
    """Build the app. with_pipeline=False skips building the AI pipeline (used by lightweight tests)."""
    # The terminology MCP server, for outside MCP clients (Claude Desktop, Inspector) at /mcp. Public data only.
    mcp_app = terminology_mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True)
    mcp_sessions = terminology_mcp.session_manager  # one per app: it can only be started once

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.deps = None
        app.state.deps_error = "pipeline disabled"
        if with_pipeline:
            from app.graph.runner import build_deps

            try:  # needs both databases reachable and an AI key
                app.state.deps = build_deps(get_settings())
            except Exception as exc:  # noqa: BLE001 — keep /health working so the problem is visible
                app.state.deps_error = str(exc).splitlines()[0][:200]
                log.error("Chat pipeline not started: %s", app.state.deps_error)

        render_url = os.environ.get("RENDER_EXTERNAL_URL")
        keep_alive_task = asyncio.create_task(_keep_alive(render_url)) if render_url else None

        async with mcp_sessions.run():
            yield

        if keep_alive_task:
            keep_alive_task.cancel()

    app = FastAPI(title="Aether — healthcare multi-database chatbot", version="0.1.0", lifespan=lifespan)
    # Let the website call this API: from localhost on any port (development), and from the addresses in
    # CORS_ORIGINS (the deployed website, e.g. on Vercel).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list(),
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(catalog_routes.router)
    app.include_router(ops_routes.router)
    app.mount("/", mcp_app)  # last: only serves /mcp, everything else above takes precedence
    return app


app = create_app()
