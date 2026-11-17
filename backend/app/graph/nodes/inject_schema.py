"""Step: INJECT SCHEMA — show the AI only the relevant pages of the table of contents.

Plain English: our databases have many tables. Showing all of them to the AI makes prompts
long, slow and error-prone. So we score each table by how many words it shares with the
question (table name, description, column names), add a big bonus when a glossary term in
the question points at that table (e.g. "HbA1c" -> observations), and keep the top few.
The patients table is always included because almost every question involves a person.
The matching glossary entries are attached too, so the AI knows exactly how to find "HbA1c".
"""

import re

from app.graph.deps import Deps
from app.graph.state import ChatState
from app.graph.timing import timed
from app.semantic.glossary import Term

MAX_TABLES = 6
STOPWORDS = {"the", "and", "for", "with", "what", "which", "how", "many", "are", "was", "were", "has", "have",
             "did", "does", "all", "any", "show", "list", "give", "who", "when", "from", "that", "this", "their",
             "they", "your", "you", "currently", "about", "there", "latest", "last"}


def _words(text: str) -> set[str]:
    words = set()
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if len(w) >= 3 and w not in STOPWORDS:
            words.add(w[:-1] if w.endswith("s") and len(w) > 3 else w)  # crude plural -> singular
    return words


def _matching_terms(question: str, terms: list[Term]) -> list[Term]:
    q = question.lower()
    q_words = _words(question)
    hits = []
    for t in terms:
        names = [n.strip().lower() for n in t.term.split("/")]
        if any(n in q for n in names) or any(_words(n) <= q_words and _words(n) for n in names):
            hits.append(t)
    return hits


@timed("inject_schema")
def inject_schema(state: ChatState, deps: Deps) -> dict:
    databases = state["route"].databases or ["clinical"]
    candidates = [t for db in databases for t in deps.catalog.for_db(db)]
    q_words = _words(state["question"])
    terms = [t for t in _matching_terms(state["question"], deps.glossary.terms) if t.db in databases]
    hinted = " ".join(t.sql_hint.lower() for t in terms)

    scores: dict[str, int] = {}
    for table in candidates:
        bag = _words(f"{table.name} {table.description or ''} " + " ".join(c.name for c in table.columns))
        score = len(q_words & bag)
        if re.search(rf"\b{table.name}\b", hinted):
            score += 3
        scores[table.name] = score

    ranked = [name for name, s in sorted(scores.items(), key=lambda kv: -kv[1]) if s > 0]
    if not ranked:  # nothing matched: show every table of the chosen database(s)
        ranked = [t.name for t in candidates]
    chosen = ranked[:MAX_TABLES]
    if "patients" in scores and "patients" not in chosen:
        chosen = ["patients", *chosen[: MAX_TABLES - 1]]

    text = deps.catalog.render(chosen)
    if terms:
        text += "\n\nGLOSSARY:\n" + "\n".join(f"- {t.term}: {t.meaning} SQL hint: {t.sql_hint}" for t in terms)
    return {"schema_text": text}
