"""The schema catalog — a "table of contents" of what the AI may query.

Plain English: when the app starts it asks each database "what tables and columns do you
have?" (this is called introspection). It keeps only the tables our glossary knows,
removes private columns (SSN, driver's licence, passport), and attaches the glossary's
plain-English descriptions. Later, the AI is shown only the few relevant tables from this
catalog — not the whole database — which keeps prompts short and answers accurate.
"""

from dataclasses import dataclass, field

from sqlalchemy import Engine, inspect, text

from app.data.synthea import is_id_column
from app.db.engines import DbName
from app.db.rls import set_query_context
from app.semantic.glossary import Glossary


MAX_CATEGORY_VALUES = 12


@dataclass
class ColumnInfo:
    name: str
    type: str
    description: str | None = None
    values: list[str] | None = None  # the few values a category column holds, e.g. ['F', 'M']


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
                notes = [n for n in (c.description, c.values and "values: " + ", ".join(f"'{v}'" for v in c.values)) if n]
                lines.append(f"  {c.name} {c.type}" + (f"  -- {'; '.join(notes)}" if notes else ""))
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)


def _category_values(engine: Engine, table: str, column: str) -> list[str] | None:
    """The distinct values of a text column, if there are only a few (e.g. gender 'F'/'M')."""
    with engine.connect() as conn, conn.begin():
        if engine.dialect.name == "postgresql":
            set_query_context(conn, "clinician", None)  # row-level security would otherwise hide every row
        rows = conn.execute(
            text(f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL LIMIT {MAX_CATEGORY_VALUES + 1}')
            if engine.dialect.name != "mysql"
            else text(f"SELECT DISTINCT `{column}` FROM `{table}` WHERE `{column}` IS NOT NULL LIMIT {MAX_CATEGORY_VALUES + 1}")
        ).scalars().all()
    return sorted(str(v) for v in rows) if 0 < len(rows) <= MAX_CATEGORY_VALUES else None


def build_catalog(engines: dict[DbName, Engine], glossary: Glossary) -> Catalog:
    """Introspect each database. Short text "category" columns also get their list of values,
    so the AI writes gender = 'F' instead of guessing gender = 'female'. Id and PII columns never do."""
    pii = set(glossary.pii_columns)
    catalog = Catalog()
    for db, engine in engines.items():
        inspector = inspect(engine)
        for table in inspector.get_table_names():
            if table not in glossary.tables:
                continue
            columns = []
            for c in inspector.get_columns(table):
                if f"{table}.{c['name']}" in pii:
                    continue
                col_type = str(c["type"]).lower()
                is_text = any(k in col_type for k in ("char", "text", "string"))
                values = _category_values(engine, table, c["name"]) if is_text and not is_id_column(c["name"]) else None
                columns.append(ColumnInfo(c["name"], col_type, glossary.columns.get(f"{table}.{c['name']}"), values))
            catalog.tables[table] = TableInfo(table, db, columns, glossary.tables[table])
    return catalog
