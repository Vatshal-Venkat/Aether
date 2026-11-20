"""The reranker: re-scores the passages the vector search found, so the best ones come first."""

import pytest

from app.config import Settings
from app.rag.rerank import RERANK_MODEL, Reranker, load_reranker, model_cached
from app.rag.store import Chunk


def chunk(text: str, drug: str = "metformin") -> Chunk:
    return Chunk(text=text, drug=drug, section="Side effects", source_url="u", distance=0.5)


def by_keyword(word: str):
    """A stand-in scorer: passages containing `word` score high."""
    calls = []

    def score(query, texts):
        calls.append((query, list(texts)))
        return [1.0 if word in t else 0.0 for t in texts]

    score.calls = calls
    return score


def test_best_passages_first_and_only_k_kept():
    scorer = by_keyword("diarrhea")
    chunks = [chunk("store at room temperature"), chunk("diarrhea and nausea"), chunk("used for diabetes")]
    out = Reranker(scorer).rerank("side effects of metformin?", chunks, k=2)
    assert [c.text for c in out] == ["diarrhea and nausea", "store at room temperature"]
    assert out[0].score == 1.0
    assert scorer.calls == [("side effects of metformin?", [c.text for c in chunks])]


def test_ties_keep_the_search_order():
    out = Reranker(lambda q, texts: [0.0] * len(texts)).rerank("q", [chunk("a"), chunk("b"), chunk("c")], k=3)
    assert [c.text for c in out] == ["a", "b", "c"]


def test_nothing_to_rerank_costs_no_model_call():
    scorer = by_keyword("x")
    assert Reranker(scorer).rerank("q", [], k=3) == []
    assert scorer.calls == []


def test_a_failing_model_falls_back_to_the_search_order():
    def broken(query, texts):
        raise RuntimeError("onnx exploded")

    out = Reranker(broken).rerank("q", [chunk("a"), chunk("b"), chunk("c")], k=2)
    assert [c.text for c in out] == ["a", "b"]


def test_switched_off_in_settings():
    assert load_reranker(Settings(_env_file=None, rag_rerank=False)) is None


@pytest.mark.skipif(not model_cached(RERANK_MODEL), reason="reranker model not downloaded on this computer")
def test_real_model_puts_the_relevant_passage_first():
    reranker = load_reranker(Settings(_env_file=None))
    assert reranker is not None
    chunks = [chunk("Store at 20 to 25 C. Keep out of reach of children."),
              chunk("WARNING: FETAL TOXICITY. When pregnancy is detected, discontinue lisinopril as soon as possible. "
                    "Drugs that act directly on the renin-angiotensin system can cause injury and death to the "
                    "developing fetus.", drug="lisinopril"),
              chunk("Lisinopril tablets are available in 10 mg strength.", drug="lisinopril")]
    out = reranker.rerank("can I take lisinopril while pregnant?", chunks, k=3)
    assert "FETAL TOXICITY" in out[0].text
