"""Loads glossary.yaml — the plain-English dictionary the AI reads before writing SQL."""

from pathlib import Path

import yaml
from pydantic import BaseModel

from app.db.engines import DbName

GLOSSARY_PATH = Path(__file__).with_name("glossary.yaml")


class Term(BaseModel):
    term: str
    meaning: str
    sql_hint: str
    db: DbName


class Glossary(BaseModel):
    tables: dict[str, str]
    columns: dict[str, str]
    terms: list[Term]
    pii_columns: list[str]
    join_keys: list[str]


def load_glossary(path: Path | None = None) -> Glossary:
    return Glossary.model_validate(yaml.safe_load((path or GLOSSARY_PATH).read_text(encoding="utf-8")))
