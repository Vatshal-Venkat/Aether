"""GET /health — is each database reachable, and is the drug-label library built?
(The AI service isn't pinged, to save free quota.)"""

from fastapi import APIRouter

from app.config import get_settings
from app.db.engines import check_db

router = APIRouter()


def check_drug_labels() -> str:
    from app.rag.store import DrugLabelStore  # imported here: ChromaDB is slow to import

    store = DrugLabelStore.open(get_settings().chroma_dir)
    if store is None:
        return "missing (run python -m scripts.build_drug_index)"
    return f"ok: {store.count()} chunks"


@router.get("/health")
def health() -> dict:
    clinical, billing = check_db("clinical"), check_db("billing")
    return {
        # The drug library is optional (SQL questions work without it), so it doesn't affect status.
        "status": "ok" if clinical == billing == "ok" else "degraded",
        "clinical": clinical,
        "billing": billing,
        "drug_labels": check_drug_labels(),
        "llm_provider": get_settings().llm_provider,
    }
