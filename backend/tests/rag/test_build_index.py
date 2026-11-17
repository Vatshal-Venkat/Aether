"""Building the drug-label library from the medications in our records (no real network)."""

import json
from pathlib import Path

import httpx

from app.rag.store import DrugLabelStore
from scripts.build_drug_index import build_index
from tests.fakes import FakeEmbedding

FIX = Path(__file__).parents[1] / "fixtures" / "openfda"


def test_build_index_counts(tmp_path):
    lisinopril = json.loads((FIX / "lisinopril.json").read_text())
    not_found = json.loads((FIX / "empty.json").read_text())

    def handler(request):
        if '"314076"' in request.url.params["search"]:
            return httpx.Response(200, json=lisinopril)
        return httpx.Response(404, json=not_found)

    store = DrugLabelStore.create(tmp_path / "chroma", embedding_function=FakeEmbedding())
    meds = [("314076", "lisinopril 10 MG Oral Tablet"), ("999", "madeupdrug 5 MG Oral Tablet")]
    summary = build_index(meds, httpx.Client(transport=httpx.MockTransport(handler)), tmp_path / "cache", store, pause=0)
    assert summary["medications"] == 2 and summary["with_label"] == 1
    assert summary["missing"] == ["madeupdrug 5 MG Oral Tablet"]
    assert summary["chunks"] > 0 and store.count() == summary["chunks"]
