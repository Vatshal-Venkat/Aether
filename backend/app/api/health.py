"""GET /health — is each database reachable, and is the drug-label library built?
(The AI service isn't pinged, to save free quota.)"""

from fastapi import APIRouter, Request

from app.config import get_settings
from app.db.engines import check_db

router = APIRouter()


def check_drug_labels(store=None) -> str:
    """Uses the pipeline's open library when there is one: /health is polled often, and opening a new ChromaDB
    client every time costs memory."""
    if store is None:
        from app.rag.store import DrugLabelStore  # imported here: ChromaDB is slow to import

        store = DrugLabelStore.open(get_settings().chroma_dir)
    if store is None:
        return "missing (run python -m scripts.build_drug_index)"
    return f"ok: {store.count()} chunks"


def memory_mb() -> dict:
    """Current and peak memory of this process (Linux, e.g. Render; empty elsewhere) — the free plan allows 512 MB."""
    try:
        import resource

        with open("/proc/self/statm") as f:
            current = int(f.read().split()[1]) * resource.getpagesize() / 1e6
        return {"memory_mb": round(current), "peak_memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e3)}
    except (ImportError, OSError):
        return {}


@router.get("/health")
def health(request: Request) -> dict:
    clinical, billing = check_db("clinical"), check_db("billing")
    deps = getattr(request.app.state, "deps", None)
    return {
        **memory_mb(),
        # The drug library is optional (SQL questions work without it), so it doesn't affect status.
        "status": "ok" if clinical == billing == "ok" else "degraded",
        "clinical": clinical,
        "billing": billing,
        "drug_labels": check_drug_labels(deps.store if deps else None),
        "llm_provider": get_settings().llm_provider,
    }
