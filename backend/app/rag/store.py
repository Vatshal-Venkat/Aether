"""The drug-label library: label passages stored in ChromaDB and searched by meaning.

Plain English: each passage is turned into a list of numbers (an "embedding") by a small AI
model that runs on this computer. Passages about similar things get similar numbers, so
"what are the side effects?" finds passages about "adverse reactions" even without the
exact words. ChromaDB is the free, local database that stores the passages with their
numbers and finds the closest ones to a question.

Every passage also carries labels (which drug, which section, link to the official label),
so a search can be limited to one drug — "side effects of lisinopril" only ever reads the
lisinopril label, never a neighbour's.
"""

import re
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from pydantic import BaseModel

from app.rag.chunking import chunk_text
from app.rag.openfda import LabelSection

COLLECTION = "drug_labels"

# Words that only say which salt/form a medicine comes in — "metformin er 500 mg" is still metformin.
FORM_WORDS = {
    "hydrochloride", "hcl", "sodium", "potassium", "calcium", "magnesium", "besylate", "succinate", "tartrate",
    "sulfate", "acetate", "maleate", "citrate", "phosphate", "bromide", "mesylate", "fumarate", "human",
    "er", "xr", "sr", "dr", "extended", "release", "delayed", "tablet", "tablets", "capsule", "capsules", "mg",
}
# Drug names too vague to match by themselves in a question (e.g. a B12 injection labelled just "vitamin").
GENERIC_NAMES = {"vitamin", "multivitamin"}


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


class Chunk(BaseModel):
    text: str
    drug: str
    section: str
    source_url: str
    distance: float
    score: float | None = None  # the reranker's relevance score (higher = better), when it ran

    @property
    def label(self) -> str:
        return f"openFDA label: {self.drug.title()} — {self.section}"


def _client(path: Path):
    # anonymized_telemetry=False: ChromaDB would otherwise send usage pings to its makers.
    return chromadb.PersistentClient(path=str(path), settings=ChromaSettings(anonymized_telemetry=False))


class DrugLabelStore:
    def __init__(self, collection):
        self.collection = collection
        self._names: list[str] | None = None
        self._descriptions: dict[str, str] = {}

    @classmethod
    def open(cls, path: Path, embedding_function=None) -> "DrugLabelStore | None":
        """The existing library, or None when it hasn't been built yet."""
        if not Path(path).exists():
            return None
        try:
            kwargs = {"embedding_function": embedding_function} if embedding_function else {}
            collection = _client(path).get_collection(COLLECTION, **kwargs)
        except Exception:  # noqa: BLE001 — missing collection
            return None
        store = cls(collection)
        return store if store.count() else None

    @classmethod
    def create(cls, path: Path, embedding_function=None, reset: bool = False) -> "DrugLabelStore":
        client = _client(path)
        if reset:
            try:
                client.delete_collection(COLLECTION)
            except Exception:  # noqa: BLE001 — nothing to delete
                pass
        kwargs = {"embedding_function": embedding_function} if embedding_function else {}
        return cls(client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"}, **kwargs))

    def add(self, sections: list[LabelSection]) -> int:
        ids, docs, metas = [], [], []
        for s in sections:
            for i, piece in enumerate(chunk_text(s.text)):
                ids.append(f"{s.rxcui}:{s.section}:{i}")
                docs.append(piece)
                metas.append({"drug": s.drug, "section": s.section, "rxcui": s.rxcui, "set_id": s.set_id,
                              "source_url": s.source_url, "med_description": s.med_description})
        for start in range(0, len(ids), 500):  # ChromaDB prefers modest batches
            self.collection.upsert(ids=ids[start:start + 500], documents=docs[start:start + 500],
                                   metadatas=metas[start:start + 500])
        self._names = None
        return len(ids)

    def count(self) -> int:
        return self.collection.count()

    def _load_names(self) -> None:
        metas = self.collection.get(include=["metadatas"])["metadatas"] or []
        self._names = sorted({m["drug"] for m in metas})
        self._descriptions = {_norm(m["med_description"]): m["drug"] for m in metas}

    def drug_names(self) -> list[str]:
        if self._names is None:
            self._load_names()
        return list(self._names)

    def drugs_in_text(self, text: str) -> list[str]:
        """Which library drugs a piece of text mentions, in order of appearance.

        A drug matches when the text IS the Synthea medication description it was fetched for
        (any case/spacing), by its full name ("insulin human"), or by its first word when the rest
        of the name is only a salt or form word ("insulin human" -> "insulin", "metformin er 500 mg"
        -> "metformin"). The first-word shortcut used to be looser and sent "sodium bicarbonate" to
        the sodium fluoride label and "penicillin G" to penicillin V (final review).
        Over-generic names ("vitamin") are only matched through their exact description.
        """
        names = self.drug_names()
        if _norm(text) in self._descriptions:
            return [self._descriptions[_norm(text)]]
        lowered = _norm(text)
        first_words: dict[str, list[str]] = {}
        for name in names:
            first_words.setdefault(name.split()[0], []).append(name)
        found: dict[str, int] = {}
        for name in names:
            if name in GENERIC_NAMES:
                continue
            words = name.split()
            candidates = [name]
            first, rest = words[0], words[1:]
            if (rest and len(first) >= 5 and first not in FORM_WORDS and len(first_words[first]) == 1
                    and all(w in FORM_WORDS or any(ch.isdigit() for ch in w) for w in rest)):
                candidates.append(first)
            for c in candidates:
                m = re.search(rf"\b{re.escape(c)}\b", lowered)
                if m:
                    found[name] = min(found.get(name, m.start()), m.start())
        return sorted(found, key=found.get)

    def search(self, query: str, drugs: list[str] | None, k: int, sections: list[str] | None = None) -> list[Chunk]:
        """The k passages closest in meaning to `query`, optionally only from these drugs / these sections."""
        return self.search_batch([query], drugs, k, sections=sections)

    def search_batch(self, queries: list[str], drugs: list[str] | None, k: int,
                     sections: list[str] | None = None) -> list[Chunk]:
        """The closest passages for multiple queries, batched into one vector store call, deduplicated."""
        if not queries:
            return []
        conditions = (([{"drug": {"$in": list(drugs)}}] if drugs else [])
                      + ([{"section": {"$in": list(sections)}}] if sections else []))
        where = conditions[0] if len(conditions) == 1 else {"$and": conditions} if conditions else None
        kwargs = {"where": where} if where else {}
        res = self.collection.query(query_texts=queries, n_results=k, **kwargs)
        chunks, seen = [], set()
        for doc_list, meta_list, dist_list in zip(res["documents"], res["metadatas"], res["distances"]):
            for text, meta, dist in zip(doc_list, meta_list, dist_list):
                key = (meta["drug"], meta["section"], text)
                if key not in seen:
                    seen.add(key)
                    chunks.append(Chunk(text=text, drug=meta["drug"], section=meta["section"],
                                        source_url=meta["source_url"], distance=float(dist)))
        return chunks
