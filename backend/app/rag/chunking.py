"""Cutting long label sections into short, overlapping passages ("chunks").

Plain English: a drug label's "Side effects" section can be pages long. Searching works best
on short passages, so we cut each section into pieces of at most ~1,200 characters,
preferably at the end of a sentence. Neighbouring pieces overlap a little (~150 characters),
so a fact that sits on a cut line still appears whole in one of them.
"""

import re

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text: str, size: int = 1200, overlap: int = 150) -> list[str]:
    text = " ".join(text.split())
    if len(text) <= size:
        return [text] if text else []
    sentences = [s for s in SENTENCE_END.split(text) if s]
    # Split any single sentence longer than `size` into hard slices.
    pieces: list[str] = []
    for s in sentences:
        pieces += [s[i:i + size] for i in range(0, len(s), size)] if len(s) > size else [s]

    chunks: list[str] = []
    current: list[str] = []
    for piece in pieces:
        if current and len(" ".join([*current, piece])) > size:
            chunks.append(" ".join(current))
            # Start the next chunk with the last sentences of this one (up to `overlap` characters).
            carry: list[str] = []
            for prev in reversed(current):
                if len(" ".join([prev, *carry])) > overlap and carry:
                    break
                carry.insert(0, prev)
            if len(" ".join([*carry, piece])) > size:
                carry = []
            current = carry
        current.append(piece)
    if current:
        chunks.append(" ".join(current))
    return chunks
