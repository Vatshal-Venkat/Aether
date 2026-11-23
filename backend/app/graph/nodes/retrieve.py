"""Step: RETRIEVE — find the right passages in the FDA drug-label library.

Plain English: like a librarian fetching the leaflet from the box instead of answering from
memory. We first work out WHICH medicines the question is about:
  * medicines named in the question ("side effects of lisinopril"), and
  * for a "hybrid" question, the medicines found in the person's records by the SQL step
    ("the medications I'm taking" -> her rows say lisinopril and metformin).
If the question names parts of the label ("boxed warning", "side effects", "interactions"...),
we read only those parts — a precise lookup instead of "closest in meaning". Then we search those
medicines' labels. If the question names only medicines that aren't in our library, we say so
rather than let the AI guess. A general question that names no medicine searches the whole library.

With the reranker on (app/rag/rerank.py), each search fetches a few more passages than needed; the reranker
reads each one together with the question and keeps the ones that answer it best, best first — so the AI reads
the most relevant passage first ("can I take lisinopril while pregnant?" -> the fetal-toxicity warning).

Query rewriting: people ask in everyday words ("while pregnant", "make me dizzy"); labels say "use in pregnancy",
"fetal toxicity", "adverse reactions". The router (same AI call, no extra one) also writes 1-2 searches in label
wording; we search with the question AND those, merge the passages, and keep the best — judged against the
person's own question. Saved with the route, so a repeated question searches exactly the same way.

We also write a short note saying what was checked: which medicines, which sections, which labels
have no such section, which medicines have no label at all, and whether some were left out (too
many to read at once). Without it, the AI once answered "only lisinopril has a boxed warning"
after reading 5 of 12 labels.
"""

import re

from app.graph.deps import Deps
from app.graph.state import ChatState
from app.graph.timing import timed

# Question wording -> label sections. Every match counts ("warnings and side effects" -> both).
# A question about warnings also reads the boxed warning — the most serious warning of all.
SECTION_WORDS: list[tuple[str, list[str]]] = [
    (r"boxed warning|black[- ]box", ["Boxed warning"]),
    (r"side[- ]effect|adverse", ["Side effects"]),
    (r"interact", ["Drug interactions"]),
    (r"contraindicat", ["Contraindications"]),
    (r"\bdos(e|es|age|ing)\b", ["Dosage"]),
    (r"used for|indicat|\buses? of\b|\bwhat (is|are) [\w\s-]{1,40}? for\??\s*$", ["Uses"]),
    (r"(?<!boxed )\bwarning|precaution", ["Warnings", "Boxed warning"]),
]
MEDICATION_COLUMNS = re.compile(r"desc|medic|drug", re.IGNORECASE)


def section_of(question: str) -> list[str]:
    q = question.lower().strip()
    found: list[str] = []
    for pattern, sections in SECTION_WORDS:
        if re.search(pattern, q):
            found += [s for s in sections if s not in found]
    return found


def _row_medicines(state: ChatState, deps: Deps) -> tuple[list[str], list[str]]:
    """(library drugs found in the rows, medication descriptions in the rows that have no label)."""
    result = state.get("result")
    found: list[str] = []
    unlabeled: list[str] = []
    if not result:
        return found, unlabeled
    med_cols = {i for i, c in enumerate(result.columns) if MEDICATION_COLUMNS.search(c)}
    for row in result.rows:
        for i, cell in enumerate(row):
            if not isinstance(cell, str):
                continue
            drugs = deps.store.drugs_in_text(cell)
            found += [d for d in drugs if d not in found]
            if not drugs and i in med_cols and cell not in unlabeled:
                unlabeled.append(cell)
    return found, unlabeled


def _section_phrase(sections: list[str]) -> str:
    quoted = ", ".join(f"'{s}'" for s in sections)
    return f"{quoted} section{'s' if len(sections) > 1 else ''}"


def search_queries(question: str, route, settings) -> list[str]:
    """The question first, then up to rag_max_rewrites of the router's label-wording rewrites (blank/repeats dropped)."""
    queries = [question]
    if settings.rag_query_rewrite:
        seen = {question.strip().lower()}
        for q in route.search_queries:
            q = " ".join(str(q).split())[:200]
            if q and q.lower() not in seen and len(queries) <= settings.rag_max_rewrites:
                seen.add(q.lower())
                queries.append(q)
    return queries


def _search(deps: Deps, question: str, queries: list[str], drugs: list[str] | None, k: int,
            sections: list[str] | None, pool: int) -> list:
    """The k best passages found by any of `queries`: the closest ones, or (with the reranker) the best k of the
    candidates, judged against the person's question."""
    fetch = k if deps.reranker is None else max(k, pool)
    candidates, seen = [], set()
    for q in queries:
        for c in deps.store.search(q, drugs, fetch, sections=sections):
            if (key := (c.drug, c.section, c.text)) not in seen:  # the same passage found twice counts once
                seen.add(key)
                candidates.append(c)
    if deps.reranker is None:
        return sorted(candidates, key=lambda c: c.distance)[:k]  # stable: one search keeps the store's order
    return deps.reranker.rerank(question, candidates, k)


def _pool(settings, k: int, searches: int) -> int:
    """Candidates per search: rag_rerank_pool x k, but never more than the per-question cap allows."""
    return min(k * settings.rag_rerank_pool, max(k, settings.rag_rerank_max_candidates // max(1, searches)))


@timed("retrieve")
def retrieve(state: ChatState, deps: Deps) -> dict:
    store, settings = deps.store, deps.settings
    if store is None:
        return {"chunks": [], "rag_problem": "no_index"}
    route = state["route"]
    question = state["question"]
    named = store.drugs_in_text(" ".join([question, *route.drugs]))
    unlabeled = [d for d in route.drugs if not store.drugs_in_text(d)]
    row_drugs, row_unlabeled = _row_medicines(state, deps) if route.kind == "hybrid" else ([], [])
    all_drugs = list(dict.fromkeys(named + row_drugs))
    unlabeled += row_unlabeled
    drugs = all_drugs[: settings.rag_max_drugs]
    sections = section_of(question)
    queries = search_queries(question, route, settings)

    notes: list[str] = []
    if unlabeled:
        notes.append(f"No label in this library for: {', '.join(unlabeled)}.")
    if drugs:
        per_drug = max(1, min(settings.rag_per_drug_k, settings.rag_max_chunks // len(drugs)))
        chunks, without = [], []
        for d in drugs:
            found = _search(deps, question, queries, [d], per_drug, sections or None,
                            _pool(settings, per_drug, len(drugs) * len(queries)))
            chunks += found
            if not found:
                without.append(d)
        if len(all_drugs) > len(drugs):
            notes.append(f"Only {len(drugs)} of {len(all_drugs)} medicines were looked up; not looked up: "
                         f"{', '.join(all_drugs[len(drugs):])}.")
        if sections:
            notes.append(f"Checked the {_section_phrase(sections)} for: {', '.join(drugs)}.")
            if without:
                notes.append(f"No {_section_phrase(sections)} in the labels of: {', '.join(without)}.")
        if route.kind == "rag" and not chunks and sections:
            # e.g. "Does amoxicillin have a boxed warning?" — "its label has none" IS the answer (final review).
            names = ", ".join(d.title() for d in without)
            many = len(without) > 1
            message = (f"The FDA label{'s' if many else ''} for {names} {'have' if many else 'has'} no "
                       f"{_section_phrase(sections)}.")
            if unlabeled:
                message += f" No label in this library for: {', '.join(unlabeled)}."
            return {"chunks": [], "rag_problem": "missing_section", "rag_message": message}
    elif route.kind == "hybrid":
        chunks = []  # the person's records mention no medicine from the library: answer from the rows
    elif route.drugs:
        return {"chunks": [], "rag_problem": "unknown_drug"}  # names only medicines we don't have
    else:
        chunks = _search(deps, question, queries, None, settings.rag_top_k, sections or None,
                         _pool(settings, settings.rag_top_k, len(queries)))
    if deps.reranker is not None and chunks:
        chunks = sorted(chunks, key=lambda c: -(c.score or 0.0))  # best first across all medicines (stable)

    labels = list(dict.fromkeys(c.label for c in chunks))
    sources = list(dict.fromkeys([*(state.get("sources") or []), *labels]))
    return {"chunks": chunks, "rag_problem": None, "sources": sources, "rag_note": " ".join(notes)}
