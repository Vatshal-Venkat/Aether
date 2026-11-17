"""Hands the pipeline toolbox (built once at startup) to each request."""

from contextlib import contextmanager

from fastapi import HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from app.graph.deps import Deps


@contextmanager
def database_errors_as_503():
    """Turn a database outage into a clear 503 instead of a 500 stack trace."""
    try:
        yield
    except SQLAlchemyError as exc:
        reason = str(getattr(exc, "orig", exc)).splitlines()[0][:150]
        raise HTTPException(status_code=503, detail=f"Database unavailable: {reason}") from exc


def get_deps(request: Request) -> Deps:
    deps = getattr(request.app.state, "deps", None)
    if deps is None:
        reason = getattr(request.app.state, "deps_error", "pipeline not started")
        raise HTTPException(status_code=503, detail=f"Chat pipeline unavailable: {reason}")
    return deps
