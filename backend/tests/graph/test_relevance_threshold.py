"""Threshold scoring: a passage scored below the cut-off doesn't reach the AI. Measured on our labels (2026-11-23):
relevant passages scored -4.2 or more, off-topic ones -6.2 or less, so the cut-off is -5.0."""

from app.graph.nodes.retrieve import relevant, retrieve
from app.graph.nodes.synthesize import synthesize
from app.graph.state import QueryResult, RouteDecision
from app.rag.store import Chunk
from tests.fakes import make_deps


def chunk(text, distance=0.4, drug="metformin", section="Warnings"):
    return Chunk(text=text, drug=drug, section=section, source_url="u", distance=distance)


class Store:
    def __init__(self, chunks):
        self.chunks = chunks

    def drugs_in_text(self, text):
        return [d for d in ("metformin", "lisinopril") if d in text.lower()]

    def search(self, query, drugs, k, sections=None):
        return [c for c in self.chunks if not drugs or c.drug in drugs][:k]


class Scores:
    """A reranker whose scores the test sets per passage text."""

    def __init__(self, scores):
        self.scores = scores

    def rerank(self, query, chunks, k):
        scored = [c.model_copy(update={"score": self.scores[c.text]}) for c in chunks]
        return sorted(scored, key=lambda c: -c.score)[:k]


def test_relevant_uses_the_reranker_score_and_falls_back_to_distance():
    s = make_deps(None).settings
    assert s.rag_min_score == -5.0 and s.rag_max_distance == 0.75
    assert relevant(chunk("a").model_copy(update={"score": -4.9}), s)
    assert not relevant(chunk("a").model_copy(update={"score": -5.1}), s)
    assert relevant(chunk("a", distance=0.74), s) and not relevant(chunk("a", distance=0.8), s)
    assert relevant(chunk("a", distance=0.99), s.model_copy(update={"rag_relevance_threshold": False}))


def test_passages_below_the_cut_off_never_reach_the_ai():
    store = Store([chunk("Lactic acidosis with alcohol."), chunk("Take with meals.", section="Dosage")])
    deps = make_deps(None, store=store, reranker=Scores({"Lactic acidosis with alcohol.": 0.5, "Take with meals.": -7.0}))
    out = retrieve({"route": RouteDecision(kind="rag", drugs=["metformin"]), "question": "Alcohol with metformin?"}, deps)
    assert [c.text for c in out["chunks"]] == ["Lactic acidosis with alcohol."]
    assert out["sources"] == ["openFDA label: Metformin — Warnings"]  # the dropped passage isn't cited either


def test_nothing_relevant_in_a_named_label_says_so_instead_of_guessing():
    store = Store([chunk("Take with meals.", section="Dosage")])
    deps = make_deps(None, store=store, reranker=Scores({"Take with meals.": -6.2}))
    out = retrieve({"route": RouteDecision(kind="rag", drugs=["metformin"]),
                    "question": "Does metformin help you learn guitar?"}, deps)
    assert out["chunks"] == [] and out["rag_problem"] == "not_relevant"
    assert out["rag_message"] == ("I checked the FDA label for Metformin, but it doesn't say anything that answers "
                                  "this question.")
    reply = synthesize({**out, "question": "q"}, deps)
    assert reply["answer"] == out["rag_message"]


def test_nothing_relevant_in_the_whole_library_says_so():
    store = Store([chunk("Penicillin dosage.", drug="penicillin")])
    deps = make_deps(None, store=store, reranker=Scores({"Penicillin dosage.": -11.0}))
    out = retrieve({"route": RouteDecision(kind="rag"), "question": "What is the capital of France?"}, deps)
    assert out["rag_problem"] == "not_relevant"
    assert out["rag_message"] == ("I searched the FDA drug labels in this library, but found nothing that answers "
                                  "this question.")


def test_hybrid_keeps_answering_from_the_records_and_tells_the_ai_what_was_dropped():
    store = Store([chunk("Take with meals.", section="Dosage"), chunk("ACE inhibitor dosage.", drug="lisinopril")])
    deps = make_deps(None, store=store, reranker=Scores({"Take with meals.": -8.0, "ACE inhibitor dosage.": 1.0}))
    rows = QueryResult(columns=["description"], rows=[["metformin 500 MG"], ["lisinopril 10 MG"]], total_rows=2,
                       truncated=False)
    out = retrieve({"route": RouteDecision(kind="hybrid", databases=["clinical"]), "question": "Can my meds hurt me?",
                    "result": rows}, deps)
    assert out["rag_problem"] is None and [c.drug for c in out["chunks"]] == ["lisinopril"]
    assert "Nothing in the labels of metformin answers this question." in out["rag_note"]
