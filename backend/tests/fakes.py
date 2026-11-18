"""Test doubles: a scripted fake AI that also records what it was asked, plus a small catalog."""

from langchain_core.messages import AIMessage

from app.config import Settings
from app.db.catalog import Catalog, ColumnInfo, TableInfo
from app.graph.deps import Deps
from app.semantic.glossary import load_glossary


class ScriptedLLM:
    """Returns the scripted replies in order; raises if asked more times than scripted."""

    def __init__(self, *replies: str | Exception):
        self.replies = list(replies)
        self.calls: list[list] = []  # every message list it received

    def invoke(self, messages, *args, **kwargs):
        self.calls.append(messages)
        if not self.replies:
            raise AssertionError("ScriptedLLM called more times than scripted")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return AIMessage(content=reply)

    def prompt_text(self, i: int = -1) -> str:
        return "\n".join(str(m.content) for m in self.calls[i])


def _cols(*names: str) -> list[ColumnInfo]:
    return [ColumnInfo(n, "text") for n in names]


def small_catalog() -> Catalog:
    g = load_glossary()
    spec = {
        "patients": _cols("id", "first", "last", "birthdate", "gender"),
        "encounters": _cols("id", "start", "patient", "provider", "encounterclass", "description", "total_claim_cost"),
        "conditions": _cols("start", "stop", "patient", "description"),
        "observations": _cols("date", "patient", "category", "description", "value", "units", "type"),
        "allergies": _cols("start", "patient", "description", "severity1"),
        "medications": _cols("start", "stop", "patient", "description", "code", "totalcost"),
    }
    billing = {
        "providers": _cols("id", "name", "speciality", "organization", "encounters", "procedures"),
        "organizations": _cols("id", "name", "city", "revenue", "utilization"),
        "payers": _cols("id", "name", "phone", "amount_covered", "revenue", "unique_customers"),
        "claims": _cols("id", "patientid", "providerid", "outstandingp", "servicedate"),
    }
    tables = {t: TableInfo(t, "clinical", cols, g.tables[t]) for t, cols in spec.items()}
    tables |= {t: TableInfo(t, "billing", cols, g.tables[t]) for t, cols in billing.items()}
    return Catalog(tables)


def make_deps(llm, engines=None, store=None, memory=None, **settings_overrides) -> Deps:
    settings = Settings(_env_file=None, **settings_overrides)
    return Deps(settings=settings, llm=llm, catalog=small_catalog(), glossary=load_glossary(), engines=engines or {},
                store=store, memory=memory)


class FakeEmbedding:
    """Deterministic stand-in for the real embedding model (no download in tests):
    each word is hashed into one of 64 slots, so texts sharing words end up close together."""

    def __new__(cls):
        import zlib

        import numpy as np
        from chromadb.api.types import EmbeddingFunction

        class _Fake(EmbeddingFunction):
            def __init__(self):
                pass

            def __call__(self, input):
                vectors = []
                for text in input:
                    v = np.zeros(64, dtype=np.float32)
                    for word in text.lower().split():
                        v[zlib.crc32(word.strip(".,;:()").encode()) % 64] += 1.0
                    norm = float(np.linalg.norm(v)) or 1.0
                    vectors.append(v / norm)
                return vectors

            @staticmethod
            def name():
                return "aether-fake"

            def get_config(self):
                return {}

            @staticmethod
            def build_from_config(config):
                return _Fake()

        return _Fake()
