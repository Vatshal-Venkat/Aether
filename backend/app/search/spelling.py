"""'Did you mean ...?' for misspelled medicine names.

Plain English: medicine names are easy to misspell, and a wrong guess about a medicine is not something to
gamble on. So before a drug question is answered, every word that is NOT a known medicine but looks very
like one (trigram similarity, app/search/trigram.py) is caught, and Aether asks back:
  * one close match:       "Did you mean metformin?"           -> Yes / No
  * two or three matches:  "Did you mean one of these: ...?"   -> each name / None of these
Each option carries the corrected question, so clicking it asks exactly that; "No" / "None of these" carry
nothing (the person just asks again). Pure Python over ~100 names: no AI call, no database — about half a
millisecond per question (the drug words and their trigrams are prepared once).
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache

from app.rag.store import FORM_WORDS
from app.search.trigram import trigrams

THRESHOLD = 0.35   # below this two spellings are different words (tuned on the drug library + everyday words)
MAX_OPTIONS = 3
MIN_LENGTH = 4
NOT_MEDICINES = {"and", "with", "oral", "patch", "system", "transdermal", "solution", "injection", "monohydrate",
                 "macrocrystals", "dihydrate", "axetil", "alfa"}


@dataclass
class SpellingSuggestion:
    word: str                      # what the person typed
    options: list[str]             # the closest medicine names, best first
    question: str                  # what Aether asks back
    option_questions: dict[str, str] = field(default_factory=dict)  # chip label -> question it sends ("" = none)


@lru_cache(maxsize=8)
def _vocabulary(drug_names: tuple[str, ...]) -> tuple[frozenset[str], dict[str, frozenset[str]], frozenset[str]]:
    """Built once per drug list: (medicine words without salts/forms like "sodium", their trigrams, every name word)."""
    words, every = set(), set()
    for name in drug_names:
        for w in re.findall(r"[a-z]+", name.lower()):
            every.add(w)
            if len(w) >= MIN_LENGTH and w not in FORM_WORDS and w not in NOT_MEDICINES:
                words.add(w)
    return frozenset(words), {w: frozenset(trigrams(w)) for w in words}, frozenset(every)


def _replace(question: str, word: str, by: str, candidates: list[str]) -> str:
    """Put `by` where the misspelling is; if a rewrite already swapped in one of the candidates, replace that."""
    for target in [word, *candidates]:
        pattern = rf"\b{re.escape(target)}\b"
        if re.search(pattern, question, flags=re.IGNORECASE):
            return re.sub(pattern, by, question, count=1, flags=re.IGNORECASE)
    return question


def suggest_drug_spelling(question: str, drug_names: list[str], correct: str | None = None) -> SpellingSuggestion | None:
    """Look for a misspelled medicine in `question`. Each option sends `correct` (default: the same question) with
    the spelling fixed — for a short follow-up ("and my metfromin?") that is the full rewritten question."""
    target = correct or question
    vocabulary, grams, every_name_word = _vocabulary(tuple(drug_names))
    for typed in re.findall(r"[A-Za-z]+", question):
        word = typed.lower()
        if len(word) < MIN_LENGTH or word in every_name_word:
            continue  # short, or spelled exactly like (part of) a medicine name
        mine = trigrams(word)
        scored = sorted(((len(mine & g) / len(mine | g), v) for v, g in grams.items()), reverse=True)
        close = [v for score, v in scored if score >= THRESHOLD][:MAX_OPTIONS]
        if not close:
            continue
        if len(close) == 1:
            ask = f"Did you mean {close[0]}?"
            options = {"Yes": _replace(target, typed, close[0], close), "No": ""}
        else:
            ask = f"Did you mean one of these: {', '.join(close)}?"
            options = {c.capitalize(): _replace(target, typed, c, close) for c in close} | {"None of these": ""}
        return SpellingSuggestion(word=typed, options=close, question=ask, option_questions=options)
    return None
