"""The toolbox every pipeline step receives: settings, the AI, the catalog, the glossary, DB engines,
and the drug-label library (None until it has been built)."""

from dataclasses import dataclass, field

from langchain_core.runnables import Runnable
from sqlalchemy import Engine

from app.config import Settings
from app.db.catalog import Catalog
from app.db.engines import DbName
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
    patient_names: dict[str, str] = field(default_factory=dict)  # patient id -> "First123 Last456"
    provider_names: list[str] = field(default_factory=list)      # doctors' names (they share surnames with patients)
