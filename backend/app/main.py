"""The FastAPI application — the "front desk" that receives questions over HTTP.

Run:  uvicorn app.main:app --reload     (from backend/)
Docs: http://localhost:8000/docs        (interactive API explorer, free with FastAPI)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import catalog_routes, chat, health
from app.config import get_settings

log = logging.getLogger(__name__)


def create_app(with_pipeline: bool = True) -> FastAPI:
    """Build the app. with_pipeline=False skips building the AI pipeline (used by lightweight tests)."""

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
        yield

    app = FastAPI(title="Aether — healthcare multi-database chatbot", version="0.1.0", lifespan=lifespan)
    # Let the future React app (served from localhost on any port) call this API.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(catalog_routes.router)
    return app


app = create_app()
