"""POST /api/chat — ask a question (and POST /api/chat/stream — the same, with live progress).

Body: {"message": "...", "role": "clinician" | "patient", "patient_id": "...", "session_id": "..."}
A patient-mode request must name an existing patient (that's the "view as" switch — no login).
"""

import json
import uuid
from collections.abc import Callable, Iterator
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.api.deps import database_errors_as_503, get_deps
from app.api.ops_routes import get_ops, rate_limit
from app.db.patients import patient_exists
from app.graph.deps import Deps
from app.graph.runner import ChatResult, run_chat, stream_chat
from app.ops import Ops
from app.service import ChatService

router = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    role: Literal["clinician", "patient"]
    patient_id: str | None = None
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    @model_validator(mode="after")
    def _patient_needs_id(self):
        if self.role == "patient" and not self.patient_id:
            raise ValueError("patient_id is required when role is 'patient'")
        return self


def get_runner() -> Callable[..., ChatResult]:
    return run_chat


def get_stream_runner() -> Callable[..., Iterator[dict]]:
    return stream_chat


async def _check_patient(req: ChatRequest, deps: Deps) -> None:
    if req.role == "patient":
        with database_errors_as_503():
            exists = await run_in_threadpool(patient_exists, deps.engines["clinical"], req.patient_id)
        if not exists:
            raise HTTPException(status_code=422, detail="Unknown patient_id")


@router.post("/chat", response_model=ChatResult, dependencies=[Depends(rate_limit)])
async def chat(req: ChatRequest, deps: Deps = Depends(get_deps), runner=Depends(get_runner),
               ops: Ops = Depends(get_ops)) -> ChatResult:
    await _check_patient(req, deps)
    service = ChatService(deps, ops)  # cache, AI queue, result pages, audit, metrics (Plan 5)
    # The pipeline is synchronous (DB drivers + AI calls); run it off the event loop.
    return await run_in_threadpool(service.answer, req.message, req.role, req.patient_id, req.session_id, runner)


@router.post("/chat/stream", dependencies=[Depends(rate_limit)])
async def chat_stream(req: ChatRequest, deps: Deps = Depends(get_deps), runner=Depends(get_stream_runner),
                      ops: Ops = Depends(get_ops)):
    """Same question, answered as Server-Sent Events: one "progress" event as each step starts
    (route, generate_sql, execute on clinical_db...), then "final" with the full result, or "error".
    The website uses the progress events to change the rhythm of the thinking orbs."""
    await _check_patient(req, deps)

    service = ChatService(deps, ops)

    def events():
        for e in service.stream(req.message, req.role, req.patient_id, req.session_id, runner):
            yield f"event: {e['event']}\ndata: {json.dumps(e['data'])}\n\n"

    # A plain (sync) generator: Starlette runs it in a worker thread, so the slow pipeline
    # never blocks the server. no-cache/no-buffering so each event reaches the browser at once.
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/sessions/{session_id}")
def session_history(session_id: str, role: Literal["clinician", "patient"], patient_id: str | None = None,
                    deps: Deps = Depends(get_deps)) -> list[dict]:
    """The turns of one conversation, oldest first: what was typed, how Aether understood it, the answer.

    Scoped like the memory itself: you must say who is asking (role, and patient_id in patient mode),
    and you only get THAT person's turns — never the clinician view's or another patient's (final review)."""
    if role == "patient" and not patient_id:
        raise HTTPException(status_code=422, detail="patient_id is required when role is 'patient'")
    if deps.memory is None:
        return []
    return [{"question": t.question, "standalone": t.standalone, "answer": t.answer, "kind": t.kind,
             "created_at": t.created_at.isoformat() if t.created_at else None}
            for t in deps.memory.turns(session_id, role, patient_id if role == "patient" else None)]
