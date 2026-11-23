"""Query rewriting for the drug-label search: the router also writes 1-2 searches in label wording
("can I take lisinopril while pregnant?" -> "lisinopril use in pregnancy fetal toxicity"), and the
retrieve step searches with the question AND those searches, then keeps the best passages."""

import json

from app.graph.nodes.retrieve import retrieve, search_queries
from app.graph.state import RouteDecision
from app.llm.prompts import route_system
from app.rag.openfda import LabelSection
from app.rag.store import Chunk, DrugLabelStore
from tests.fakes import FakeEmbedding, ScriptedLLM, make_deps
from app.graph.runner import run_chat

QUESTION = "Can I take lisinopril while expecting a baby?"
FETAL = "Fetal toxicity: drugs acting on the renin-angiotensin system can cause injury and death to the developing fetus."


class SpyStore:
    """A drug-label store that answers each search query with passages given by the test, and remembers the queries."""

    def __init__(self, answers: dict[str, list[Chunk]]):
        self.answers, self.queries = answers, []

    def drugs_in_text(self, text):
        return ["lisinopril"] if "lisinopril" in text.lower() else []

    def search(self, query, drugs, k, sections=None):
        self.queries.append((query, drugs, k))
        return self.answers.get(query, [])[:k]


def chunk(text, distance, drug="lisinopril", section="Warnings"):
    return Chunk(text=text, drug=drug, section=section, source_url="u", distance=distance)


def state(route, question=QUESTION):
    return {"route": route, "question": question}


def test_search_queries_are_the_question_plus_the_rewrites_without_repeats():
    route = RouteDecision(kind="rag", search_queries=["lisinopril pregnancy fetal toxicity", "  ", QUESTION.upper(),
                                                      "lisinopril pregnancy fetal toxicity", "third", "fourth"])
    settings = make_deps(None).settings
    assert search_queries(QUESTION, route, settings) == [QUESTION, "lisinopril pregnancy fetal toxicity", "third"]
    assert search_queries(QUESTION, route, settings.model_copy(update={"rag_query_rewrite": False})) == [QUESTION]
    assert search_queries(QUESTION, RouteDecision(kind="rag"), settings) == [QUESTION]


def test_retrieve_searches_with_every_query_and_keeps_the_closest_passages():
    rewrite = "lisinopril use in pregnancy fetal toxicity"
    store = SpyStore({QUESTION: [chunk("Take lisinopril once a day.", 0.6, section="Dosage"), chunk("Cough.", 0.7)],
                      rewrite: [chunk(FETAL, 0.2), chunk("Cough.", 0.7)]})
    deps = make_deps(None, store=store, rag_per_drug_k=2)
    out = retrieve(state(RouteDecision(kind="rag", drugs=["lisinopril"], search_queries=[rewrite])), deps)
    assert [q for q, *_ in store.queries] == [QUESTION, rewrite]
    assert all(drugs == ["lisinopril"] for _, drugs, _ in store.queries)  # still only that medicine's label
    assert [c.text for c in out["chunks"]] == [FETAL, "Take lisinopril once a day."]  # closest first, no duplicates


def test_reranker_judges_the_merged_passages_against_the_original_question():
    rewrite = "lisinopril use in pregnancy fetal toxicity"
    store = SpyStore({QUESTION: [chunk("Take lisinopril once a day.", 0.6)], rewrite: [chunk(FETAL, 0.2)]})

    class Spy:
        def rerank(self, query, chunks, k):
            self.query, self.texts = query, [c.text for c in chunks]
            scored = [c.model_copy(update={"score": float("fetus" in c.text)}) for c in chunks]
            return sorted(scored, key=lambda c: -c.score)[:k]

    spy = Spy()
    deps = make_deps(None, store=store, reranker=spy, rag_per_drug_k=1)
    out = retrieve(state(RouteDecision(kind="rag", drugs=["lisinopril"], search_queries=[rewrite])), deps)
    assert spy.query == QUESTION                      # relevance is judged against what the person asked
    assert sorted(spy.texts) == sorted(["Take lisinopril once a day.", FETAL])
    assert [c.text for c in out["chunks"]] == [FETAL]


def test_rewrites_share_the_reranker_candidate_cap():
    store = SpyStore({})
    deps = make_deps(None, store=store, reranker=type("R", (), {"rerank": lambda self, q, c, k: c[:k]})(),
                     rag_top_k=6, rag_rerank_pool=3, rag_rerank_max_candidates=36)
    retrieve(state(RouteDecision(kind="rag", search_queries=["a b", "c d"]), "Which medicines cause low blood sugar?"),
             deps)
    assert len(store.queries) == 3 and sum(k for *_, k in store.queries) <= 36


def test_router_is_asked_for_label_wording_searches():
    prompt = route_system("clinician")
    assert '"search_queries"' in prompt and "label" in prompt
    assert RouteDecision(kind="sql").search_queries == []


def test_end_to_end_a_rewrite_finds_the_passage_the_plain_question_misses(tmp_path):
    s = DrugLabelStore.create(tmp_path / "c", embedding_function=FakeEmbedding())
    s.add([LabelSection(drug="lisinopril", section=sec, text=t, rxcui="1", set_id="x", source_url="u",
                        med_description="lisinopril 10 MG Oral Tablet")
           for sec, t in [("Dosage", "Take lisinopril once a day, can be taken with a baby aspirin while fasting."),
                          ("Warnings", "Lisinopril fetal toxicity: use in pregnancy can cause fetal injury and death.")]])
    route = json.dumps({"kind": "rag", "databases": [], "reason": "t", "drugs": ["lisinopril"],
                        "search_queries": ["lisinopril fetal toxicity use in pregnancy"]})
    llm = ScriptedLLM(route, "Lisinopril is not safe in pregnancy. Source: openFDA label: Lisinopril — Warnings")
    result = run_chat(make_deps(llm, store=s, rag_per_drug_k=1), QUESTION, "clinician", None, "s")
    assert [d.label for d in result.documents] == ["openFDA label: Lisinopril — Warnings"]
