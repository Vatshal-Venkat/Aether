"""GET /health — is each database reachable? (The AI service isn't pinged, to save free quota.)"""

from fastapi import APIRouter

from app.config import get_settings
from app.db.engines import check_db

router = APIRouter()


@router.get("/health")
def health() -> dict:
    clinical, billing = check_db("clinical"), check_db("billing")
    return {
        "status": "ok" if clinical == billing == "ok" else "degraded",
        "clinical": clinical,
        "billing": billing,
        "llm_provider": get_settings().llm_provider,
    }
