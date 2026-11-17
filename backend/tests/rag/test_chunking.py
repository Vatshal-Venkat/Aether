"""Cutting long label sections into overlapping passages."""

from app.rag.chunking import chunk_text


def _sentences(n):
    return " ".join(f"Sentence number {i} talks about a side effect in some detail." for i in range(n))


def test_chunk_short_text_single_chunk():
    assert chunk_text("Short text.") == ["Short text."]


def test_chunk_long_text_overlaps_and_limits():
    text = _sentences(90)  # ~5,500 characters
    chunks = chunk_text(text, size=1200, overlap=150)
    assert len(chunks) >= 5
    assert all(len(c) <= 1200 for c in chunks)
    for a, b in zip(chunks, chunks[1:]):
        last_sentence = a.rstrip().split(". ")[-1]
        assert last_sentence.rstrip(".") in b  # consecutive chunks share text
    for i in range(90):
        assert any(f"Sentence number {i} " in c for c in chunks)  # nothing lost


def test_chunk_breaks_at_sentence_end():
    chunks = chunk_text(_sentences(40), size=1200, overlap=150)
    assert all(c.rstrip().endswith(".") for c in chunks[:-1])
