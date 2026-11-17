"""One-command database setup.

Plain English: this script builds the two "rooms" of our library from scratch.
  1. Gets the Synthea CSV files (downloads them only if they're not on disk).
  2. Creates the databases: clinical_db in PostgreSQL, billing_db in MySQL.
  3. Copies each CSV into the right database as a table.
  4. Adds a primary key (a unique label per row) and an index (a fast lookup list) on
     the patient column, so searches by patient are quick.
  5. Creates the read-only account "chatbot_ro" the chatbot uses — it can look, never change.
  6. Switches on PostgreSQL row-level security (patient privacy filter).

Run from backend/:   python -m scripts.setup_databases          (rebuild tables)
                     python -m scripts.setup_databases --reset  (drop databases first)
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from app.config import Settings, get_settings
from app.data.synthea import PATIENT_COLUMN, TABLE_SPLIT, download_synthea, load_table, sql_dtypes

RO_USER = "chatbot_ro"


def _sql_literal(value: str) -> str:
    """Quote a value for DDL statements that can't take bind parameters (e.g. CREATE ROLE ... PASSWORD)."""
    return "'" + value.replace("'", "''") + "'"


def _server_url(db_url: str, database: str | None) -> str:
    return make_url(db_url).set(database=database).render_as_string(hide_password=False)


def create_databases(s: Settings, reset: bool) -> None:
    pg_server = create_engine(_server_url(s.clinical_url(admin=True), "postgres"), isolation_level="AUTOCOMMIT")
    with pg_server.connect() as conn:
        if reset:
            conn.execute(text("DROP DATABASE IF EXISTS clinical_db WITH (FORCE)"))
        if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'clinical_db'")).scalar():
            conn.execute(text("CREATE DATABASE clinical_db"))
    pg_server.dispose()

    my_server = create_engine(_server_url(s.billing_url(admin=True), None))
    with my_server.begin() as conn:
        if reset:
            conn.execute(text("DROP DATABASE IF EXISTS billing_db"))
        conn.execute(text("CREATE DATABASE IF NOT EXISTS billing_db CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"))
    my_server.dispose()


def load_tables(engine: Engine, kind: str, csv_dir) -> None:
    for table, target in TABLE_SPLIT.items():
        if target != kind:
            continue
        df = load_table(csv_dir / f"{table}.csv")
        if engine.dialect.name == "mysql":
            # MySQL DATETIME has no time zone: store UTC without the zone marker.
            for col in df.columns:
                if isinstance(df[col].dtype, pd.DatetimeTZDtype):
                    df[col] = df[col].dt.tz_convert(None)
        df.to_sql(table, engine, if_exists="replace", index=False, chunksize=1000, method="multi",
                  dtype=sql_dtypes(df))
        with engine.begin() as conn:
            if "id" in df.columns and df["id"].notna().all() and df["id"].is_unique:
                conn.execute(text(f"ALTER TABLE {table} ADD PRIMARY KEY (id)"))
            pcol = PATIENT_COLUMN.get(table)
            if pcol and pcol != "id":
                conn.execute(text(f"CREATE INDEX ix_{table}_{pcol} ON {table} ({pcol})"))
        print(f"  loaded {kind}.{table}: {len(df):,} rows")


def create_readonly_users(s: Settings, pg: Engine, my: Engine) -> None:
    pw = _sql_literal(s.ro_password)
    with pg.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :u"), {"u": RO_USER}).scalar()
        verb = "ALTER" if exists else "CREATE"
        conn.execute(text(f"{verb} ROLE {RO_USER} WITH LOGIN PASSWORD {pw}"))
        conn.execute(text(f"GRANT CONNECT ON DATABASE clinical_db TO {RO_USER}"))
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {RO_USER}"))
        conn.execute(text(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {RO_USER}"))
    with my.begin() as conn:
        conn.execute(text(f"CREATE USER IF NOT EXISTS '{RO_USER}'@'localhost' IDENTIFIED BY :pw"), {"pw": s.ro_password})
        conn.execute(text(f"ALTER USER '{RO_USER}'@'localhost' IDENTIFIED BY :pw"), {"pw": s.ro_password})
        conn.execute(text(f"GRANT SELECT ON billing_db.* TO '{RO_USER}'@'localhost'"))
    print(f"  read-only user '{RO_USER}' ready in both databases")


RLS_TEMPLATE = Path(__file__).parent / "sql" / "postgres_rls.sql"


def apply_postgres_rls(pg: Engine) -> None:
    """Switch on the patient privacy filter for every clinical table that holds patient data."""
    template = "\n".join(
        line for line in RLS_TEMPLATE.read_text().splitlines() if not line.lstrip().startswith("--")
    )
    with pg.begin() as conn:
        for table, kind in TABLE_SPLIT.items():
            if kind != "clinical" or table not in PATIENT_COLUMN:
                continue
            for statement in template.format(table=table, patient_col=PATIENT_COLUMN[table]).split(";"):
                if statement.strip():
                    conn.execute(text(statement))
    print("  row-level security on for all clinical patient tables")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="drop both databases before rebuilding")
    args = parser.parse_args(argv)

    s = get_settings()
    missing = [n for n in ("pg_admin_password", "mysql_admin_password", "ro_password") if not getattr(s, n)]
    if missing:
        print("Missing in backend/.env: " + ", ".join(m.upper() for m in missing), file=sys.stderr)
        return 1

    print("1/5 Synthea data")
    csv_dir = download_synthea(s.data_dir)
    print(f"  using {csv_dir}")
    print("2/5 Creating databases")
    create_databases(s, args.reset)
    pg = create_engine(s.clinical_url(admin=True))
    my = create_engine(s.billing_url(admin=True))
    print("3/5 Loading tables")
    load_tables(pg, "clinical", csv_dir)
    load_tables(my, "billing", csv_dir)
    print("4/5 Read-only users")
    create_readonly_users(s, pg, my)
    print("5/5 Row-level security")
    apply_postgres_rls(pg)
    pg.dispose()
    my.dispose()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
