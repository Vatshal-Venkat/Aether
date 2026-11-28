"""Live openFDA fallback: labels fetched by name when the library lacks a medicine or isn't built (no network)."""

from app.graph.nodes import retrieve as retrieve_mod
from app.rag import live
from app.rag.store import Chunk
from tests.graph.test_rag import ask, route, store  # noqa: F401 — pytest fixture
from tests.fakes import ScriptedLLM


def label(generic, brand="", **sections):
    return {"openfda": {"generic_name": [generic], "brand_name": [brand] if brand else []}, "set_id": "x",
            **{k: [v] for k, v in sections.items()}}


def test_best_label_prefers_single_ingredient():
    combo, single = label("SITAGLIPTIN AND METFORMIN HYDROCHLORIDE"), label("METFORMIN HYDROCHLORIDE")
    assert live.best_label([combo, single], "METFORMIN") is single
    assert live.best_label([label("SEMAGLUTIDE", "OZEMPIC"), label("X")], "OZEMPIC")["openfda"]["brand_name"] == ["OZEMPIC"]
    assert live.best_label([], "X") is None


def test_live_chunks_keeps_asked_sections_and_reports_missing(monkeypatch, tmp_path):
    labels = {"SEMAGLUTIDE": label("SEMAGLUTIDE", adverse_reactions="Nausea, vomiting.", dosage_and_administration="Weekly.")}
    monkeypatch.setattr(live, "fetch_by_name", lambda _c, name, _d: labels.get(name))
    chunks, missing = live.live_chunks(["semaglutide", "nodrug"], ["Side effects"], tmp_path)
    assert [(c.drug, c.section, c.text) for c in chunks] == [("semaglutide", "Side effects", "Nausea, vomiting.")]
    assert missing == ["nodrug"]


def fake_live(names, sections, _dir):
    return [Chunk(text="Nausea.", drug=n.lower(), section="Side effects", source_url="u", distance=0.0)
            for n in names if n.lower() != "nodrug"], [n for n in names if n.lower() == "nodrug"]


def test_unknown_drug_answered_live(monkeypatch, store):  # noqa: F811
    monkeypatch.setenv("RAG_LIVE_FALLBACK", "true")
    monkeypatch.setattr(retrieve_mod, "live_chunks", fake_live)
    llm = ScriptedLLM(route("rag", drugs=["Ozempic"]), "Nausea. Source: openFDA label: Ozempic — Side effects")
    result = ask(llm, "What are the side effects of Ozempic?", store)
    assert "Nausea" in result.answer and [d.label for d in result.documents] == ["openFDA label: Ozempic — Side effects"]


def test_no_library_answered_live(monkeypatch):
    monkeypatch.setenv("RAG_LIVE_FALLBACK", "true")
    monkeypatch.setattr(retrieve_mod, "live_chunks", fake_live)
    llm = ScriptedLLM(route("rag", drugs=["metformin"]), "Nausea. Source: openFDA label: Metformin — Side effects")
    result = ask(llm, "What are the side effects of metformin?", None)
    assert "Nausea" in result.answer and result.documents


def test_no_library_and_nothing_found_live_says_not_loaded(monkeypatch):
    monkeypatch.setenv("RAG_LIVE_FALLBACK", "true")
    monkeypatch.setattr(retrieve_mod, "live_chunks", fake_live)
    result = ask(ScriptedLLM(route("rag", drugs=["nodrug"])), "Side effects of nodrug?", None)
    assert "isn't loaded yet" in result.answer
