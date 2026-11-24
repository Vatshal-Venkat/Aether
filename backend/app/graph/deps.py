"""The toolbox every pipeline step receives: settings, the AI, the catalog, the glossary, DB engines,
and the drug-label library (None until it has been built)."""

from dataclasses import dataclass, field

from langchain_core.runnables import Runnable
from sqlalchemy import Engine

from app.config import Settings
from app.db.catalog import Catalog
from app.db.engines import DbName
from app.llm.usage import UsageLedger
from app.memory.saved_queries import SavedQueryStore
from app.memory.store import ConversationStore
from app.rag.rerank import Reranker
from app.rag.store import DrugLabelStore
from app.semantic.glossary import Glossary


@dataclass
class Deps:
    settings: Settings
    llm: Runnable
    catalog: Catalog
    glossary: Glossary
    engines: dict[DbName, Engine]
    store: DrugLabelStore | None = None
    memory: ConversationStore | None = None  # conversation turns (follow-ups)
    patient_names: dict[str, str] = field(default_factory=dict)  # patient id -> "First123 Last456"
    provider_names: list[str] = field(default_factory=list)      # doctors' names (they share surnames with patients)
    models: list[str] = field(default_factory=list)  # AI models in fallback order: main, backup, last resort
    usage: UsageLedger | None = None                 # tokens used / limits per model (the "model limits" panel)
    saved_queries: SavedQueryStore | None = None   # same question -> same SQL (None = always write it afresh)
    reranker: Reranker | None = None                 # re-scores drug-label passages (None = keep the search order)
    fast_llm: Runnable | None = None                 # fast model for routing/contextualizing (None = uses llm)
