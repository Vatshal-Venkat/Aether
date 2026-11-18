"""Service endpoints (Plan 5): result pages, the audit log, live metrics — and the rate-limit check.

  GET /api/results/{id}?page=n&role=…&patient_id=…  the next 100 rows of a big table (only for whoever asked)
  GET /api/audit?limit=50                            the logbook (OFF unless ENABLE_AUDIT_API=true)
  GET /metrics                                       live counters, Prometheus text format
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST

from app.config import get_settings
from app.ops import Ops

router = APIRouter()


def get_ops(request: Request) -> Ops:
    """The one Ops kit for this app, created on first use (tests swap in a temporary one)."""
    ops = getattr(request.app.state, "ops", None)
    if ops is None:
        ops = request.app.state.ops = Ops.from_settings(get_settings())
    return ops


def rate_limit(request: Request, ops: Ops = Depends(get_ops)) -> None:
    """Refuse (HTTP 429) when one address asks too many questions in a minute."""
    key = request.client.host if request.client else "unknown"
    allowed, retry_after = ops.limiter.allow(key)
    if not allowed:
        ops.metrics.rate_limited()
        raise HTTPException(status_code=429, detail="Too many questions at once — please wait a moment.",
                            headers={"Retry-After": str(max(1, round(retry_after)))})


@router.get("/api/results/{result_id}")
def result_page(result_id: str, role: Literal["clinician", "patient"], page: int = Query(1, ge=1),
                patient_id: str | None = None, ops: Ops = Depends(get_ops)) -> dict:
    owner = (role, patient_id if role == "patient" else None)
    try:
        found = ops.results.page(result_id, page, owner=owner)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if found is None:
        raise HTTPException(status_code=404, detail="This table has expired or isn't yours — ask the question again.")
    return found


@router.get("/api/audit")
def audit(limit: int = Query(50, ge=1, le=500), ops: Ops = Depends(get_ops)) -> list[dict]:
    if not ops.audit_api_enabled:
        # No login in this project: an open logbook would show every patient's questions to anyone.
        raise HTTPException(status_code=404, detail="The audit API is off. Set ENABLE_AUDIT_API=true to turn it on.")
    return [e.model_dump(mode="json") for e in ops.audit.recent(limit)]


@router.get("/metrics")
def metrics(ops: Ops = Depends(get_ops)) -> Response:
    return Response(ops.metrics.render(), media_type=CONTENT_TYPE_LATEST)
