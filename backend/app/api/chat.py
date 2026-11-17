"""POST /api/chat — ask a question.

Body: {"message": "...", "role": "clinician" | "patient", "patient_id": "...", "session_id": "..."}
A patient-mode request must name an existing patient (that's the "view as" switch — no login).
"""

import uuid
from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, model_validator

from app.api.deps import database_errors_as_503, get_deps
from app.db.patients import patient_exists
from app.graph.deps import Deps
from app.graph.runner import ChatResult, run_chat

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


@router.post("/chat", response_model=ChatResult)
async def chat(req: ChatRequest, deps: Deps = Depends(get_deps), runner=Depends(get_runner)) -> ChatResult:
    if req.role == "patient":
        with database_errors_as_503():
            exists = await run_in_threadpool(patient_exists, deps.engines["clinical"], req.patient_id)
        if not exists:
            raise HTTPException(status_code=422, detail="Unknown patient_id")
    # The pipeline is synchronous (DB drivers + AI calls); run it off the event loop.
    return await run_in_threadpool(runner, deps, req.message, req.role, req.patient_id, req.session_id)
