"""Saved queries — the same question always runs the same SQL, so it always gives the same numbers.

Plain English: the AI writes SQL afresh for every question, and two fresh tries can differ a little: one counts
"(disorder)" diagnoses only, another every diabetes row; one returns a row per patient, another a row per diagnosis;
the backup model writes it differently again. So the same question could give different results on different days.

Now, the first time a question is answered cleanly, we save how it was answered: the route, the plan (which
database(s)) and each step's SQL. Asking the same question again (ignoring case, spacing and punctuation) reuses
exactly that SQL: same rows -> same numbers. Only the wording of the answer is written fresh. If the data changes,
the saved SQL simply runs on the new data.

Follow-ups ("show their names") are saved under the previous question + what was typed, together with the full
question the AI rewrote them into — that rewrite can vary too, so it is reused (and the "Understood as" line with it).

Reworded questions ("How many people have diabetes?" after "How many patients have diabetes?"): a small local model
scores how alike two questions are, but a score alone can't be trusted — measured, "How many patients do NOT have
diabetes?" scored 0.912 and "How many FEMALE patients have diabetes?" 0.891, while the true rewording "number of
diabetic patients" scored only 0.876. So match_kind() also compares the meaningful words:
  * never the same question: a negation, an opposite (most/fewest, male/female...), a number, or "now" differs;
  * the same question (reused silently, shown as "Understood as: <saved question>"): the same meaningful words once
    wording like "how many / number of / people / diabetic" is evened out, in the same order;
  * not sure (similar, but different words): Aether asks "Do you mean ...?" — Yes reuses it, No answers fresh.
In patient mode only the patient's own earlier questions are offered, so nobody sees another person's wording.

Safety and freshness:
  * saved SQL still goes through every check (validate, row filter, privacy) before it runs;
  * what's saved is the SQL before the patient filter is added, and patient-mode SQL that names the patient
    is never saved — a saved query never carries one person's id to another;
  * only clean answers are saved (no unverified numbers, no errors, no clarifying questions);
  * questions about "now" ("last month", "today", "this year") are not saved — fixed dates would go stale;
  * when the glossary or the AI's SQL rules change, the version changes and old saved queries are ignored;
  * a saved query that stops working is rewritten by the AI and replaced;
  * python -m scripts.forget_saved_queries empties the store.

Stored in backend/data/saved_queries.sqlite (not uploaded to git).
"""

import datetime as dt
import hashlib
import json
import math
import re
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.db.engines import DbName
from app.graph.state import Link, PlanStep, RouteDecision

NOW_WORDS = re.compile(
    r"\b(today|yesterday|tomorrow|tonight|now|current(ly)?|recent(ly)?|latest|this (week|month|year|quarter)|"
    r"(last|past|previous|next|coming) (\d+ )?(days?|weeks?|months?|years?|quarters?)|ago|so far|to date)\b",
    re.IGNORECASE)

# ---- comparing two questions ----------------------------------------------------------------------------------
SAME_IF_SAME_WORDS = 0.75   # same meaningful words (same order) and at least this alike -> the same question
ASK_FROM = 0.80             # different words but at least this alike -> ask "Do you mean ...?"

PHRASES = [  # evened out before comparing words (longest first)
    (r"\binsurance compan(y|ies)\b", "insurer"), (r"\bhealth insurers?\b", "insurer"), (r"\bpayers?\b", "insurer"),
    (r"\binsurers\b", "insurer"), (r"\bhow many\b", "count"), (r"\bnumber of\b", "count"), (r"\btotal\b", "count"),
    (r"\b(been )?diagnosed with\b", ""), (r"\bthere\b", ""),
]
SYNONYMS = {
    "people": "patient", "person": "patient", "persons": "patient", "diabetic": "diabetes", "diabetics": "diabetes",
    "doctors": "doctor", "providers": "doctor", "provider": "doctor", "physicians": "doctor", "physician": "doctor",
    "hospitals": "hospital", "visits": "visit", "encounters": "visit", "encounter": "visit",
    "medicines": "medication", "drugs": "medication", "meds": "medication", "medications": "medication",
}
STOP = set("""a an the of in on at for to with by from and or is are was were be been being do does did have has had
which what who whom whose there their them they it its this that these those me my i we our you your please show tell
give can could would will get find about as per each any all""".split())
NEGATIONS = {"not", "no", "without", "never", "none", "except", "excluding", "nobody"}
OPPOSITES = [
    ({"most", "highest", "largest", "biggest", "maximum", "max", "top", "more", "greatest"},
     {"least", "fewest", "lowest", "smallest", "minimum", "min", "bottom", "less", "fewer"}),
    ({"male", "men", "man", "boys"}, {"female", "women", "woman", "girls"}),
    ({"alive", "living"}, {"dead", "died", "deceased"}),
    ({"before"}, {"after"}),
    ({"first", "earliest", "oldest"}, {"last", "latest", "newest"}),
    ({"increase", "increased", "rise"}, {"decrease", "decreased", "fall"}),
]
ENTITIES = {"patient", "doctor", "insurer", "hospital", "visit", "medication", "claim"}

MatchKind = Literal["same", "ask"] | None


def _words(question: str) -> list[str]:
    q = question.lower().replace("n't", " not")
    for pattern, by in PHRASES:
        q = re.sub(pattern, by, q)
    out = []
    for w in re.findall(r"[a-z0-9]+", q):
        w = SYNONYMS.get(w, w)
        if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is", "es")):
            w = w[:-1]  # patients -> patient, customers -> customer
        out.append(SYNONYMS.get(w, w))
    return out


def _opposed(a: set[str], b: set[str]) -> bool:
    return any((a & x and b & y and not (a & y)) or (a & y and b & x and not (a & x)) for x, y in OPPOSITES)


def match_kind(asked: str, saved: str, score: float) -> MatchKind:
    """Is `asked` the same question as `saved` (alike by `score`, 0-1)? "same", "ask" (not sure) or None (different)."""
    a, b = _words(asked), _words(saved)
    sa, sb = set(a), set(b)
    if NOW_WORDS.search(asked) or NOW_WORDS.search(saved):
        return None  # about "now": never matched
    if (sa & NEGATIONS) != (sb & NEGATIONS) or _opposed(sa, sb):
        return None
    if {w for w in a if w.isdigit()} != {w for w in b if w.isdigit()}:
        return None  # top 5 vs top 10
    content_a, content_b = [w for w in a if w not in STOP], [w for w in b if w not in STOP]
    same_words = set(content_a) == set(content_b)
    same_order = [w for w in content_a if w in ENTITIES] == [w for w in content_b if w in ENTITIES]
    if same_words and same_order and score >= SAME_IF_SAME_WORDS:
        return "same"
    return "ask" if score >= ASK_FROM else None


# ---- what is saved ------------------------------------------------------------------------------------------------
class SavedSql(BaseModel):
    step: int
    db: DbName
    sql: str


class SavedQuery(BaseModel):
    route: RouteDecision
    plan: list[PlanStep]
    link: Link | None = None
    sql: list[SavedSql]
    standalone: str | None = None  # a follow-up's full question ("show their names" -> "What are the names of ...")
    question: str | None = None    # the question as it was first asked (shown in "Do you mean ...?")
    saved_at: dt.datetime | None = None


class Match(BaseModel):
    kind: Literal["same", "ask"]
    query: SavedQuery
    question: str   # the saved question, as first asked
    score: float


SIMILAR_ASK = "I've answered a very similar question before: “{}” Do you mean the same thing?"
SIMILAR_PREFIX = SIMILAR_ASK.split("“")[0]
YES, NO = "Yes, the same question", "No, something different"
ASSUME_ASK = "To answer this I'd have to assume: {}. Is that what you mean?"
ASSUME_PREFIX = ASSUME_ASK.split("{}")[0]
GO_AHEAD, SOMETHING_ELSE = "Yes, go ahead", "No, I mean something else"


def with_assumptions(question: str, assumptions: list[str]) -> str:
    return f"{question.strip()} ({'; '.join(assumptions)})"


def assumption_accepted(history: list[dict], typed: str) -> bool:
    """Is `typed` the "Yes, go ahead" click on the last turn's "I'd have to assume ..." question?"""
    if not history or history[-1].get("kind") != "clarification":
        return False
    last = history[-1]
    if not str(last.get("answer", "")).startswith(ASSUME_PREFIX):
        return False
    before = normalize_question(last.get("question", ""))
    return normalize_question(typed) != before and normalize_question(typed).startswith(before)


def similar_ask_reply(history: list[dict], typed: str) -> Literal["yes", "no"] | None:
    """Is `typed` a click on the last turn's "Do you mean ...?" buttons? Yes sends the saved question, No re-sends
    the person's own question (which must then be answered fresh — never asked about again)."""
    if not history or history[-1].get("kind") != "clarification":
        return None
    last = history[-1]
    if not str(last.get("answer", "")).startswith(SIMILAR_PREFIX):
        return None
    quoted = re.search(r"“(.+?)”", last["answer"])
    if quoted and normalize_question(typed) == normalize_question(quoted.group(1)):
        return "yes"
    if normalize_question(typed) == normalize_question(last.get("question", "")):
        return "no"
    return None


def normalize_question(question: str) -> str:
    """Same question whatever the case, spacing or end punctuation. Synthea names keep their digits."""
    q = " ".join(question.lower().split())
    return q.strip(" ?!.,;:\"'")


def follow_up_key(previous: str, typed: str) -> str:
    """A follow-up is saved under the question before it + what was typed: the AI's rewrite of it can vary, this can't."""
    return f"{normalize_question(previous)} >> {normalize_question(typed)}"


def worth_saving(question: str) -> bool:
    return not NOW_WORDS.search(question)


def rules_version(*texts: str) -> str:
    """A fingerprint of everything that shapes the SQL (glossary, SQL rules, schema): change one -> new version."""
    return hashlib.sha256("\x1f".join(texts).encode()).hexdigest()[:16]


def _cosine(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


Embed = Callable[[list[str]], list[list[float]]]


class SavedQueryStore:
    def __init__(self, path: Path, version: str, embed: Embed | None = None):
        """`embed` turns questions into vectors (a small local model) for matching reworded questions; without it
        only exact questions are matched."""
        self.path, self.version, self.embed = Path(path), version, embed
        self._lock = threading.Lock()
        self._ready = False

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        if not self._ready:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                conn.execute("CREATE TABLE IF NOT EXISTS queries (role TEXT, question TEXT, version TEXT, owner TEXT, "
                             "body TEXT, vector TEXT, saved_at TEXT, PRIMARY KEY (role, question, version))")
                self._ready = True
        return conn

    def get(self, role: str, question: str) -> SavedQuery | None:
        with self._connect() as conn:
            row = conn.execute("SELECT body FROM queries WHERE role = ? AND question = ? AND version = ?",
                               (role, normalize_question(question), self.version)).fetchone()
        return SavedQuery.model_validate_json(row[0]) if row else None

    def save(self, role: str, question: str, query: SavedQuery, owner: str | None = None,
             comparable: bool = True) -> None:
        """Save under `question`. `comparable`: also usable for reworded questions (not for follow-up keys)."""
        query = query.model_copy(update={"saved_at": dt.datetime.now(dt.timezone.utc),
                                         "question": query.question or question})
        vector = None
        if comparable and self.embed is not None:
            try:
                vector = json.dumps([round(x, 5) for x in self.embed([question])[0]])
            except Exception:  # noqa: BLE001 — without a vector it still matches exact questions
                vector = None
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO queries VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (role, normalize_question(question), self.version, owner, query.model_dump_json(), vector,
                          query.saved_at.isoformat()))

    def similar(self, role: str, question: str, owner: str | None = None) -> Match | None:
        """The saved question this one most likely rewords — "same" (reuse), "ask" (not sure), or None.
        In patient mode (owner set) only that patient's own saved questions are considered."""
        if self.embed is None:
            return None
        sql = "SELECT body, vector FROM queries WHERE role = ? AND version = ? AND vector IS NOT NULL"
        args: list = [role, self.version]
        if owner is not None:
            sql += " AND owner = ?"
            args.append(owner)
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        if not rows:
            return None
        here = self.embed([question])[0]
        scored = sorted(((_cosine(here, json.loads(v)), SavedQuery.model_validate_json(b)) for b, v in rows),
                        key=lambda x: -x[0])
        for score, query in scored[:5]:  # the closest few: the first one that isn't ruled out
            kind = match_kind(question, query.question or "", score)
            if kind is not None:
                return Match(kind=kind, query=query, question=query.question or "", score=round(score, 3))
        return None

    def forget(self, role: str | None = None, question: str | None = None) -> int:
        """Delete one saved query (role + question), or all of them. Returns how many were deleted."""
        with self._connect() as conn:
            if role is not None and question is not None:
                cur = conn.execute("DELETE FROM queries WHERE role = ? AND question = ?", (role, normalize_question(question)))
            else:
                cur = conn.execute("DELETE FROM queries")
            return cur.rowcount

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT count(*) FROM queries").fetchone()[0]
