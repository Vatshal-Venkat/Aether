"""Hands the pipeline toolbox (built once at startup) to each request."""

from fastapi import HTTPException, Request

from app.graph.deps import Deps


def get_deps(request: Request) -> Deps:
    deps = getattr(request.app.state, "deps", None)
    if deps is None:
        reason = getattr(request.app.state, "deps_error", "pipeline not started")
        raise HTTPException(status_code=503, detail=f"Chat pipeline unavailable: {reason}")
    return deps
