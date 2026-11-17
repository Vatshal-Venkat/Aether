"""The toolbox every pipeline step receives: settings, the AI, the catalog, the glossary, DB engines."""

from dataclasses import dataclass

from langchain_core.runnables import Runnable
from sqlalchemy import Engine

from app.config import Settings
from app.db.catalog import Catalog
from app.db.engines import DbName
from app.semantic.glossary import Glossary


@dataclass
class Deps:
    settings: Settings
    llm: Runnable
    catalog: Catalog
    glossary: Glossary
    engines: dict[DbName, Engine]
