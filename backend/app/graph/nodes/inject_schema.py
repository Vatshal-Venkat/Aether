"""Step: INJECT SCHEMA — show the AI only the relevant pages of the table of contents.

Plain English: our databases have many tables. Showing all of them to the AI makes prompts
long, slow and error-prone. So we score each table by how many words it shares with the
question (table name, description, column names), add a big bonus when a glossary term in
the question points at that table (e.g. "HbA1c" -> observations), and keep the top few.
The patients table is always included because almost every question involves a person.
The matching glossary entries are attached too, so the AI knows exactly how to find "HbA1c".
For a two-step plan, only the current step's database and sub-question are used, and the table
that links the two steps is always shown. In patient mode, population totals are left out.
"""

import re

from app.graph.deps import Deps
from app.graph.state import ChatState
from app.graph.steps import current_step
from app.graph.timing import timed
from app.semantic.glossary import Term
from app.terminology.client import render_hints

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
    step = current_step(state)
    databases = [step.db]
    candidates = deps.catalog.for_db(step.db)
    q_words = _words(step.goal)
    terms = [t for t in _matching_terms(step.goal, deps.glossary.terms) if t.db in databases]
    hinted = " ".join(t.sql_hint.lower() for t in terms)
    link = state.get("link")
    link_table = (link.from_table if state.get("step", 0) == 0 else link.to_table) if link else None

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
    if link_table and link_table not in chosen:  # the table that connects the two steps must be shown
        chosen = [link_table, *chosen[: MAX_TABLES - 1]]
    route = state.get("route")
    if route and route.kind == "hybrid" and "medications" in scores and "medications" not in chosen:
        # A records + drug-label question is about someone's medicines. Accuracy report (HY03):
        # "what is my metformin USED for" matched "supplies ... USED during visits" instead.
        chosen = ["medications", *chosen[: MAX_TABLES - 1]]

    # Patient mode: hide population totals (PII is already absent from the catalog).
    hidden = deps.glossary.blocked_columns(state["role"]) - set(deps.glossary.pii_columns)
    text = deps.catalog.render(chosen, hidden=hidden)
    if terms:
        text += "\n\nGLOSSARY:\n" + "\n".join(f"- {t.term}: {t.meaning} SQL hint: {t.sql_hint}" for t in terms)
    if deps.terminology and route and route.conditions and step.db == "clinical":
        hints = render_hints(deps.terminology.lookup(route.conditions))
        if hints:
            text += "\n\n" + hints
    return {"schema_text": text}
