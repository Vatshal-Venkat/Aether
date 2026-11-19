"""Trigram similarity — how alike two spellings are.

Plain English: a word is cut into overlapping 3-letter pieces ("metformin" -> "  m", " me", "met", "etf",
"tfo", ...). Two spellings are similar when they share many pieces: score = shared pieces / all distinct
pieces, from 0 (nothing alike) to 1 (identical). A typo changes only a few pieces, so "metfromin" still
scores about 0.43 against "metformin", while different words ("warnings" vs "warfarin") score low.
This is the same method as PostgreSQL's pg_trgm extension, done in plain Python: no database, no AI,
microseconds per comparison.
"""

import re


def trigrams(text: str) -> set[str]:
    grams: set[str] = set()
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        padded = f"  {word} "
        grams |= {padded[i:i + 3] for i in range(len(padded) - 2)}
    return grams


def similarity(a: str, b: str) -> float:
    ta, tb = trigrams(a), trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
