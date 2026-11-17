"""The schema catalog — a "table of contents" of what the AI may query.

Plain English: when the app starts it asks each database "what tables and columns do you
have?" (this is called introspection). It keeps only the tables our glossary knows,
removes private columns (SSN, driver's licence, passport), and attaches the glossary's
plain-English descriptions. Later, the AI is shown only the few relevant tables from this
catalog — not the whole database — which keeps prompts short and answers accurate.
"""

from dataclasses import dataclass, field

from sqlalchemy import Engine, inspect

from app.db.engines import DbName
from app.semantic.glossary import Glossary


@dataclass
class ColumnInfo:
    name: str
    type: str
    description: str | None = None


@dataclass
class TableInfo:
    name: str
    db: DbName
    columns: list[ColumnInfo]
    description: str | None = None


@dataclass
class Catalog:
    tables: dict[str, TableInfo] = field(default_factory=dict)

    def for_db(self, db: DbName) -> list[TableInfo]:
        return sorted((t for t in self.tables.values() if t.db == db), key=lambda t: t.name)

    def allowed_tables(self, db: DbName) -> set[str]:
        return {t.name for t in self.tables.values() if t.db == db}

    def render(self, table_names: list[str]) -> str:
        """Compact text for the AI prompt: one block per table, one line per column."""
        blocks = []
        for name in table_names:
            t = self.tables.get(name)
            if t is None:
                continue
            lines = [f"TABLE {t.name}" + (f"  -- {t.description}" if t.description else "")]
            for c in t.columns:
                lines.append(f"  {c.name} {c.type}" + (f"  -- {c.description}" if c.description else ""))
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)


def build_catalog(engines: dict[DbName, Engine], glossary: Glossary) -> Catalog:
    pii = set(glossary.pii_columns)
    catalog = Catalog()
    for db, engine in engines.items():
        inspector = inspect(engine)
        for table in inspector.get_table_names():
            if table not in glossary.tables:
                continue
            columns = [
                ColumnInfo(name=c["name"], type=str(c["type"]).lower(), description=glossary.columns.get(f"{table}.{c['name']}"))
                for c in inspector.get_columns(table)
                if f"{table}.{c['name']}" not in pii
            ]
            catalog.tables[table] = TableInfo(table, db, columns, glossary.tables[table])
    return catalog
