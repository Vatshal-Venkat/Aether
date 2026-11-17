"""GET /api/patients (for the "view as patient" picker) and GET /api/schema (for a schema sidebar)."""

from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.api.deps import get_deps
from app.db.patients import list_patients
from app.graph.deps import Deps

router = APIRouter(prefix="/api")


@router.get("/patients")
async def patients(deps: Deps = Depends(get_deps)) -> list[dict]:
    return await run_in_threadpool(list_patients, deps.engines["clinical"])


@router.get("/schema")
def schema(db: Literal["clinical", "billing"] = "clinical", deps: Deps = Depends(get_deps)) -> list[dict]:
    return [
        {
            "table": t.name,
            "description": t.description,
            "columns": [{"name": c.name, "type": c.type, "description": c.description} for c in t.columns],
        }
        for t in deps.catalog.for_db(db)
    ]
