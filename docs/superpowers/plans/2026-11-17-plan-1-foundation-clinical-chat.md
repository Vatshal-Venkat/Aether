# Plan 1 — Foundation + Clinical Chat (Milestones 1–2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load Synthea data into PostgreSQL `clinical_db` and MySQL `billing_db` with read-only access and Postgres row-level security, then answer plain-English questions about `clinical_db` through a LangGraph pipeline exposed by FastAPI.

**Architecture:** A setup script downloads Synthea CSVs and loads them into two databases. The FastAPI app builds a schema catalog + glossary at startup, and a LangGraph graph of small node functions (route → inject_schema → generate_sql → validate → execute → [retry] → synthesize → verify_numbers) answers questions using a free-tier cloud LLM (Groq default). Patient mode is enforced in Postgres by RLS via transaction-local settings.

**Tech Stack:** Python 3.13, FastAPI 0.163, Uvicorn, LangGraph 1.2, langchain-core 1.8, langchain-groq / langchain-google-genai / langchain-ollama, SQLAlchemy 2.1, psycopg 3.3 (binary), PyMySQL 1.2 + cryptography, sqlglot 30, pandas 3.1, pydantic-settings 2.16, PyYAML, httpx, pytest 9.

**Spec:** `docs/superpowers/specs/2026-11-17-healthcare-multidb-chatbot-design.md`

**Later plans (not this one):** Plan 2 = MySQL querying, multi-DB routing/planning/merge, MySQL row-filter rewrite, patient-mode population-column blocklist. Plan 3 = RAG + hybrid. Plan 4 = conversation memory, clarification, SSE streaming. Plan 5 = caching, pagination, rate/concurrency limits, audit, metrics. Plan 6 = evaluation harness.

## Global Constraints

- All backend code under `backend/`; Python package `app`; tests under `backend/tests/`; commands run from `backend/` with the venv active (`py -3.13 -m venv .venv`; if a dependency lacks 3.13 wheels, use `py -3.12`).
- Secrets only in `backend/.env` (git-ignored). `backend/.env.example` committed with placeholder values. Never log or send passwords/API keys to the LLM.
- Databases: PostgreSQL 18 `clinical_db` on `localhost:5432`; MySQL 8.4 `billing_db` on `localhost:3306`. Chatbot connects only as read-only user `chatbot_ro` in each. Admin credentials are used only by `scripts/setup_databases.py`.
- Table split (exact): clinical = patients, encounters, conditions, observations, medications, procedures, immunizations, allergies, careplans, devices, imaging_studies, supplies; billing = organizations, providers, payers, payer_transitions, claims, claims_transactions.
- All column names lower-cased on load.
- PII columns `patients.ssn`, `patients.drivers`, `patients.passport`: never in the LLM schema text, rejected by the validator, stripped from results.
- LLM provider via `LLM_PROVIDER` = `groq` (default) | `gemini` | `ollama`. All LLM calls go through `app/llm/client.py`.
- Limits: `SQL_TIMEOUT_SECONDS=10`, `MAX_SQL_ATTEMPTS=3`, `ROWS_STORED_CAP=1000`, `ROWS_TO_LLM=50`.
- Every graph node is a small function with a plain-English docstring explaining what it does and why (the owner is learning from the code).
- Tests needing real databases are marked `@pytest.mark.db` and auto-skip with a clear reason when the DB is unreachable. Tests never call a real LLM; they use `langchain_core.language_models.fake_chat_models.FakeListChatModel`.
- Synthea source URL: `https://synthetichealth.github.io/synthea-sample-data/downloads/latest/synthea_sample_data_csv_latest.zip` (111 patients; claims.csv has 8275 rows).

## Review Focus

1. **Identity switching inside a query** — SQL calling `set_config(...)`/`current_setting(...)` (e.g. `SELECT * FROM patients WHERE set_config('app.patient_id','<other>',true) IS NOT NULL`) must be rejected by the validator, so a patient can't change who they are mid-query. → Task 7 test `test_rejects_identity_functions`.
2. **`SELECT *` reaching PII** — `SELECT *`, `p.*`, or a join exposing `patients.ssn` must be rejected, and the executor must still strip PII columns if any slip through. → Task 7 `test_rejects_star_on_pii_table`, Task 10 `test_execute_strips_pii_columns`.
3. **Legitimately empty answers** — a patient with no allergies must get "No records found…", not three retries or an invented answer. → Task 10 `test_empty_result_does_not_retry`.
4. **Messy LLM output** — SQL wrapped in prose, ```sql fences, trailing `;`, or a hidden second statement after a comment must be extracted cleanly or rejected, never executed as two statements. → Task 9 `test_extract_sql_variants`, Task 7 `test_rejects_multiple_statements`.
5. **LLM provider down / rate-limited (HTTP 429)** — the user gets a response with `kind="error"` and a friendly message, not a 500 stack trace. → Task 12 `test_llm_failure_returns_error_kind`.

---

### Task 1: Project scaffold and settings

**Files:**
- Create: `backend/requirements.txt`, `backend/pyproject.toml` (pytest config + `db` marker only), `backend/.env.example`, `.gitignore` (root), `backend/app/__init__.py`, `backend/app/config.py`, `backend/tests/__init__.py`, `backend/tests/conftest.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `class Settings(BaseSettings)` and `get_settings() -> Settings` (lru-cached). Fields (env names upper-case): `pg_host="localhost"`, `pg_port=5432`, `pg_admin_user="postgres"`, `pg_admin_password`, `mysql_host="localhost"`, `mysql_port=3306`, `mysql_admin_user="root"`, `mysql_admin_password`, `ro_password` (shared by both `chatbot_ro` users), `llm_provider: Literal["groq","gemini","ollama"]="groq"`, `groq_api_key: str|None`, `groq_model="openai/gpt-oss-120b"`, `gemini_api_key: str|None`, `gemini_model="gemini-2.5-flash"`, `ollama_base_url="http://localhost:11434"`, `ollama_model="qwen2.5-coder:7b"`, `sql_timeout_seconds=10`, `max_sql_attempts=3`, `rows_stored_cap=1000`, `rows_to_llm=50`, `data_dir=Path("data")`. Properties: `clinical_url(admin: bool=False) -> str` (`postgresql+psycopg://…/clinical_db`), `billing_url(admin: bool=False) -> str` (`mysql+pymysql://…/billing_db?charset=utf8mb4`). Passwords URL-encoded.
- Produces (conftest): fixture `settings` returning `Settings(_env_file=None, **test values)`; helper `requires_db(kind: Literal["clinical","billing"])` that skips when a connection as `chatbot_ro` fails.

- [ ] **Step 1: Write failing tests** — `test_defaults` (llm_provider == "groq", sql_timeout_seconds == 10, max_sql_attempts == 3), `test_clinical_url_uses_ro_user` (contains `chatbot_ro@localhost:5432/clinical_db`), `test_admin_url_uses_admin_user`, `test_password_is_url_encoded` (password `p@ss/word` → `p%40ss%2Fword` in URL), `test_env_override` (monkeypatch `LLM_PROVIDER=gemini`).
- [ ] **Step 2: Run** `python -m pytest tests/test_config.py -v` → FAIL (module missing).
- [ ] **Step 3: Implement** requirements (pin `>=` the versions in Tech Stack; `psycopg[binary]`), `.env.example` (every field, placeholder secrets), `.gitignore` (`.venv/`, `backend/.env`, `backend/data/`, `__pycache__/`, `.pytest_cache/`), `config.py`.
- [ ] **Step 4: Run** tests → PASS.
- [ ] **Step 5: Commit** `feat: backend scaffold and settings`.

### Task 2: Synthea download and table preparation

**Files:**
- Create: `backend/app/data/__init__.py`, `backend/app/data/synthea.py`
- Test: `backend/tests/test_synthea.py`, fixture `backend/tests/fixtures/mini_synthea/` (3 tiny CSVs: `patients.csv`, `encounters.csv`, `claims.csv`, 2–3 rows each, real Synthea headers)

**Interfaces:**
- Produces: `TABLE_SPLIT: dict[str, Literal["clinical","billing"]]` (exact split from Global Constraints); `PATIENT_COLUMN: dict[str, str]` (table → column holding the patient id: `patients→"id"`, `claims→"patientid"`, `claims_transactions→"patientid"`, every other table with patients → `"patient"`; reference tables absent); `download_synthea(dest_dir: Path) -> Path` (downloads + extracts once, returns the folder containing the CSVs; skips if present); `load_table(csv_path: Path) -> pandas.DataFrame` (lower-cased columns, date columns parsed); `sql_dtypes(df: DataFrame) -> dict[str, sqlalchemy.types.TypeEngine]` (id-like columns → `String(64)`).
- Id-like columns = `id`, `patient`, `patientid`, `encounter`, `provider`, `providerid`, `organization`, `payer`, `claimid`, `chargeid`, plus any column ending in `id`. Date columns = `start`, `stop`, `date`, `birthdate`, `deathdate`, `servicedate`, `currentillnessdate`, `lastbilleddate1`, `lastbilleddate2`, `lastbilleddatep`, `fromdate`, `todate`, `start_date`, `end_date` — parsed with `pd.to_datetime(..., utc=True, format="ISO8601")`.

- [ ] **Step 1: Write failing tests** — `test_split_covers_all_18_tables` (len == 18; clinical has 12, billing 6), `test_patient_column_map` (`PATIENT_COLUMN["patients"] == "id"`, `["claims"] == "patientid"`, `"providers" not in PATIENT_COLUMN`), `test_load_table_lowercases_and_parses_dates` (fixture encounters: `"start"` in columns, dtype is datetime), `test_sql_dtypes_id_columns_are_varchar64`, `test_download_skips_when_present` (pre-create folder with a CSV; monkeypatch httpx to raise if called).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `synthea.py` (download with `httpx.stream`, extract with `zipfile`, find the folder containing `patients.csv`).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: synthea download and table preparation`.

### Task 3: Database setup script, read-only users, Windows install guide

**Files:**
- Create: `backend/scripts/__init__.py`, `backend/scripts/setup_databases.py`, `docs/setup-windows.md`
- Test: `backend/tests/test_setup_databases.py` (`@pytest.mark.db`, runs after the owner has run the script)

**Interfaces:**
- Consumes: `get_settings()`, `TABLE_SPLIT`, `download_synthea`, `load_table`, `sql_dtypes`.
- Produces: CLI `python -m scripts.setup_databases [--reset]`. Steps, in order: download → create DBs (Postgres via admin on `postgres` DB with AUTOCOMMIT; `--reset` drops with `WITH (FORCE)`; MySQL `CREATE DATABASE … CHARACTER SET utf8mb4`) → load each table with `DataFrame.to_sql(if_exists="replace", chunksize=1000, method="multi", dtype=sql_dtypes(df))` into its DB → primary key on `id` where the column exists and is unique; index on the patient column per `PATIENT_COLUMN` → create `chatbot_ro` (Postgres: `LOGIN`, `CONNECT`, `USAGE ON SCHEMA public`, `SELECT ON ALL TABLES IN SCHEMA public`; MySQL: `'chatbot_ro'@'localhost'`, `SELECT ON billing_db.*`) → apply RLS (Task 4) → print row counts per table. Idempotent without `--reset` (re-running replaces tables and re-grants).
- `docs/setup-windows.md`: install PostgreSQL 18 (EDB installer: Server, pgAdmin 4, Command Line Tools; port 5432), MySQL 8.4 LTS MSI (Development Computer, port 3306, Windows service), optional Ollama + DBeaver, free Groq key (console.groq.com) and optional Gemini key (aistudio.google.com), create venv, `pip install -r requirements.txt`, copy `.env.example` → `.env` and fill, run the setup script, run `python -m pytest`. Each step with a one-line plain-English "why".

- [ ] **Step 1: Write failing tests** (db-marked) — `test_clinical_counts` (via the **admin** URL, so it stays valid after Task 4 enables RLS: `patients` = 111, `encounters` = 5059), `test_billing_counts` (`claims` = 8275, `providers` = 267), `test_ro_cannot_write_postgres` (INSERT into patients raises `ProgrammingError`/permission denied), `test_ro_cannot_write_mysql`, `test_columns_lowercase` (information_schema shows `birthdate`, not `BIRTHDATE`).
- [ ] **Step 2: Run** → SKIPPED (no DB) or FAIL (DB present, not loaded).
- [ ] **Step 3: Implement** the script and the guide.
- [ ] **Step 4: Owner runs** `python -m scripts.setup_databases --reset` → prints counts; then `python -m pytest tests/test_setup_databases.py -v` → PASS.
- [ ] **Step 5: Commit** `feat: database setup script and windows guide`.

### Task 4: PostgreSQL row-level security

**Files:**
- Create: `backend/scripts/sql/postgres_rls.sql`, `backend/app/db/__init__.py`, `backend/app/db/rls.py`
- Modify: `backend/scripts/setup_databases.py` (run the SQL after grants)
- Test: `backend/tests/test_rls.py` (`@pytest.mark.db`)

**Interfaces:**
- Produces: SQL enabling RLS on every clinical table in `PATIENT_COLUMN`, one policy per table for `chatbot_ro`: `USING (current_setting('app.role', true) = 'clinician' OR <patient_col> = current_setting('app.patient_id', true))`. Unset settings → no rows (safe default). Generate the per-table statements from `PATIENT_COLUMN` in the script rather than hand-writing 12 copies (the .sql file holds the template).
- Produces: `set_query_context(conn: sqlalchemy.Connection, role: Literal["clinician","patient"], patient_id: str|None) -> None` — runs `SELECT set_config('app.role', :role, true), set_config('app.patient_id', :pid, true)` inside the current transaction (transaction-local, so pooled connections never carry a previous user's identity). Raises `ValueError` if role is patient and patient_id is falsy.

- [ ] **Step 1: Write failing tests** — `test_clinician_sees_all` (111), `test_patient_sees_only_self` (count 1, and that row's id == the chosen id), `test_patient_sees_only_own_encounters` (all `patient` values == id), `test_no_context_sees_nothing` (0 rows), `test_or_1_equals_1_cannot_escape` (`SELECT count(*) FROM patients WHERE 1=1 OR id IS NOT NULL` → 1 in patient mode), `test_context_does_not_leak_across_transactions` (patient txn, then new txn without context → 0), `test_patient_role_requires_id` (ValueError, no DB needed — not db-marked).
- [ ] **Step 2: Run** → FAIL/SKIP.
- [ ] **Step 3: Implement** SQL, script hook, `rls.py`. Re-run setup script.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: postgres row-level security for patient mode`.

### Task 5: Engines and health endpoint

**Files:**
- Create: `backend/app/db/engines.py`, `backend/app/main.py`, `backend/app/api/__init__.py`, `backend/app/api/health.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `DbName = Literal["clinical","billing"]`; `get_engine(db: DbName) -> sqlalchemy.Engine` (cached; read-only URL; `pool_pre_ping=True`, `pool_size=5`; Postgres `connect_args={"options": f"-c statement_timeout={ms}"}`; MySQL: on `connect` event run `SET SESSION MAX_EXECUTION_TIME=<ms>`); `check_db(db: DbName) -> str` ("ok" or "error: <short message>").
- Produces: `create_app() -> FastAPI` in `main.py` (module-level `app = create_app()`), CORS for `http://localhost:*` and `http://127.0.0.1:*` origins (regex), `GET /health` → `{"status": "ok"|"degraded", "clinical": str, "billing": str, "llm_provider": str}`. LLM is not pinged on health (saves free quota).

- [ ] **Step 1: Write failing tests** — `test_health_ok` (monkeypatch `check_db` → "ok": status "ok"), `test_health_degraded` (billing returns "error: refused" → status "degraded", HTTP 200), `test_cors_allows_localhost_vite` (Origin `http://localhost:5173` preflight allowed).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; also `uvicorn app.main:app` and open `http://localhost:8000/health` against real DBs → both "ok".
- [ ] **Step 5: Commit** `feat: db engines and health endpoint`.

### Task 6: Schema catalog and glossary

**Files:**
- Create: `backend/app/semantic/__init__.py`, `backend/app/semantic/glossary.yaml`, `backend/app/semantic/glossary.py`, `backend/app/db/catalog.py`
- Test: `backend/tests/test_glossary.py`, `backend/tests/test_catalog.py`

**Interfaces:**
- Produces (`glossary.py`): `Glossary` pydantic model: `tables: dict[str, str]` (table → description), `columns: dict[str, str]` (`"table.column"` → description), `terms: list[Term]` (`term`, `meaning`, `sql_hint`, `db: DbName`), `pii_columns: list[str]` (`"patients.ssn"`, `"patients.drivers"`, `"patients.passport"`), `join_keys: list[str]` (e.g. `"encounters.provider = providers.id"`); `load_glossary(path: Path|None=None) -> Glossary`.
- `glossary.yaml` content: description for all 18 tables; descriptions for the non-obvious columns (e.g. `observations.value` stored as text — cast for numbers; `observations.category`; `encounters.encounterclass`; `medications.stop` NULL = still active; `conditions.stop` NULL = ongoing; `patients.deathdate` NULL = alive; Synthea names carry digit suffixes like `Abe604`); at least these terms: HbA1c (`observations.description ILIKE '%Hemoglobin A1c%'`), active medication, ongoing condition, diabetes, blood pressure, BMI, cholesterol, visit/encounter, age (from birthdate), the cost authority rule from spec §7.
- Produces (`catalog.py`): `ColumnInfo(name: str, type: str, description: str|None)`, `TableInfo(name: str, db: DbName, columns: list[ColumnInfo], description: str|None)`, `class Catalog` with `tables: dict[str, TableInfo]`, `for_db(db: DbName) -> list[TableInfo]`, `render(table_names: list[str]) -> str` (compact prompt text: `table(col type -- desc, …) -- table desc`), `allowed_tables(db: DbName) -> set[str]`; `build_catalog(engines: dict[DbName, Engine], glossary: Glossary) -> Catalog` via `sqlalchemy.inspect`, dropping PII columns.

- [ ] **Step 1: Write failing tests** — `test_glossary_loads`, `test_glossary_tables_match_split` (keys == set(TABLE_SPLIT)), `test_glossary_pii_list`; catalog tests build from an in-memory SQLite engine standing in for clinical (create `patients(id, first, ssn, birthdate)`): `test_catalog_drops_pii` ("ssn" not in rendered text, not in columns), `test_render_includes_descriptions`, `test_allowed_tables`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: schema catalog and semantic glossary`.

### Task 7: SQL validator

**Files:**
- Create: `backend/app/safety/__init__.py`, `backend/app/safety/sql_validator.py`
- Test: `backend/tests/test_sql_validator.py`

**Interfaces:**
- Produces: `Dialect = Literal["postgres","mysql"]`; `ValidationResult(ok: bool, sql: str|None, error: str|None)` (dataclass); `validate_sql(sql: str, dialect: Dialect, allowed_tables: set[str], blocked_columns: set[str], default_limit: int) -> ValidationResult`; `tables_in(sql: str, dialect: Dialect) -> list[str]` (sorted, CTE names excluded).
- Rules (in order; first failure returns an `error` phrased as an instruction the LLM can act on): parses with `sqlglot.parse(sql, read=dialect)`; exactly one statement; root is `Select`/`Union`/`With`→select (no `Insert/Update/Delete/Merge/Create/Drop/Alter/TruncateTable/Command/Grant` anywhere in the tree); no `INTO` (incl. `INTO OUTFILE`); **function ALLOW-list** (amended after final review: a blocklist missed `query_to_xml()`, which runs SQL hidden in a string and let patient mode read every patient); every real table in `allowed_tables`, with real-vs-CTE resolved **per scope** (amended after review: a CTE named after a real table hid that table from all checks); no column in `blocked_columns` (`"table.column"` or bare name matched against tables in the query); no `*` / `t.*` when any referenced table has a blocked column; adds `LIMIT default_limit` to the outermost select if absent. Returns the regenerated SQL in the target dialect.

- [ ] **Step 1: Write failing tests** (pure, no DB) — `test_accepts_simple_select`, `test_accepts_cte_and_join`, `test_rejects_dml` (parametrize INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/TRUNCATE/GRANT), `test_rejects_multiple_statements` (`SELECT 1; DROP TABLE patients` and `SELECT 1 -- x\n; DELETE FROM patients`), `test_rejects_into_outfile` (mysql), `test_rejects_identity_functions` (the set_config example from Review Focus 1; `current_setting('app.role')`), `test_rejects_sleep`, `test_rejects_unknown_table`, `test_rejects_pii_column` (`SELECT ssn FROM patients`, `SELECT p.passport FROM patients p`), `test_rejects_star_on_pii_table` (`SELECT * FROM patients`, `SELECT p.* FROM patients p JOIN encounters e ON …`), `test_allows_star_on_safe_table` (`SELECT * FROM conditions`), `test_adds_limit` (result contains `LIMIT 1000`), `test_keeps_existing_limit`, `test_tables_in`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: AST-based SQL validator`.

### Task 8: LLM client

**Files:**
- Create: `backend/app/llm/__init__.py`, `backend/app/llm/client.py`
- Test: `backend/tests/test_llm_client.py`

**Interfaces:**
- Produces: `class LLMConfigError(Exception)`; `get_chat_model(settings: Settings) -> BaseChatModel` — builds the provider from `settings.llm_provider` (`ChatGroq(model=…, temperature=0)`, `ChatGoogleGenerativeAI(…)`, `ChatOllama(…)`), wrapped with `.with_retry(stop_after_attempt=4, wait_exponential_jitter=True)` for rate-limit/connection errors, and `.with_fallbacks([...])` to any *other* provider whose key is configured (Ollama included only if `ollama_model` set and reachable is NOT checked at build time). Missing key for the selected provider → `LLMConfigError("Set GROQ_API_KEY in backend/.env …")`.
- Produces: `ask_json(llm: Runnable, system: str, user: str, schema: type[T]) -> T` — asks for JSON only, extracts the first `{…}` block, validates with pydantic; one repair retry including the validation error; raises `LLMOutputError` after that. `ask_text(llm: Runnable, system: str, user: str) -> str`.

- [ ] **Step 1: Write failing tests** — `test_groq_selected_by_default` (with a fake key, underlying model class is `ChatGroq`; no network), `test_missing_key_raises_config_error`, `test_ask_json_parses_fenced_json` (FakeListChatModel returns "Sure! ```json {\"kind\":\"sql\"} ```"), `test_ask_json_repairs_once` (first response invalid, second valid → success), `test_ask_json_gives_up` (two invalid → `LLMOutputError`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Verify live once** (not a test): `python -c` snippet calling `ask_text(get_chat_model(get_settings()), "Reply OK", "ping")` → prints a reply. While here, list Groq's current models (`GET https://api.groq.com/openai/v1/models` with the key) and set `GROQ_MODEL` default to the best available free model if `openai/gpt-oss-120b` is gone.
- [ ] **Step 6: Commit** `feat: pluggable LLM client`.

### Task 9: Graph state, route, inject_schema, generate_sql

**Files:**
- Create: `backend/app/graph/__init__.py`, `backend/app/graph/state.py`, `backend/app/graph/deps.py`, `backend/app/graph/timing.py`, `backend/app/llm/prompts.py`, `backend/app/graph/nodes/__init__.py`, `backend/app/graph/nodes/route.py`, `backend/app/graph/nodes/inject_schema.py`, `backend/app/graph/nodes/generate_sql.py`
- Test: `backend/tests/graph/test_route.py`, `test_inject_schema.py`, `test_generate_sql.py`

**Interfaces:**
- Produces (`state.py`): `RouteKind = Literal["sql","out_of_scope","refuse"]`; `RouteDecision(BaseModel)`: `kind`, `databases: list[DbName]`, `reason: str`; `SqlAttempt(TypedDict)`: `sql: str`, `error: str|None`; `QueryResult(BaseModel)`: `columns: list[str]`, `rows: list[list[Any]]` (JSON-safe), `total_rows: int`, `truncated: bool`; `ChatState(TypedDict, total=False)`: `question`, `role`, `patient_id`, `session_id`, `route: RouteDecision`, `schema_text: str`, `attempts: list[SqlAttempt]`, `final_sql: str|None`, `db: DbName`, `result: QueryResult|None`, `answer: str`, `kind: Literal["answer","refusal","out_of_scope","error"]`, `sources: list[str]`, `unverified_numbers: list[str]`, `timings: Annotated[dict[str,float], merge_dicts]` where `merge_dicts(a: dict, b: dict) -> dict` (defined in `state.py`) returns `{**a, **b}` so each node adds its timing without erasing others.
- Produces (`deps.py`): `@dataclass Deps`: `settings`, `llm: Runnable`, `catalog: Catalog`, `glossary: Glossary`, `engines: dict[DbName, Engine]`. Nodes have signature `(state: ChatState, deps: Deps) -> dict` (partial update); wired with `functools.partial`.
- Produces (`timing.py`): decorator `timed(name: str)` that adds `{"timings": {name: seconds}}` to the node's returned dict.
- Produces nodes: `route(state, deps)` → `{"route": RouteDecision}` via `ask_json`; prompt (in `prompts.py`) describes clinical_db only in this plan, includes the role; patient role + question about other people or population statistics → `refuse`; non-health/data questions → `out_of_scope`. `inject_schema(state, deps)` → `{"schema_text"}`: `catalog.render` of tables relevant to the question — select by keyword overlap with table names/descriptions/glossary terms (top 6), always including `patients`; plus matching glossary terms. `generate_sql(state, deps)` → `{"attempts": attempts + [{"sql": sql, "error": None}]}` via `ask_text` then `extract_sql(text) -> str` (module-level function: takes the first ```sql fenced block, else the text from the first `SELECT`/`WITH`; strips trailing `;` and whitespace). Prompt includes dialect (PostgreSQL), schema_text, glossary terms, today's date, rules (only listed columns, never PII, LIMIT, cast `observations.value` when comparing numbers), and on retry the previous SQL + error.

- [ ] **Step 1: Write failing tests** — `test_route_parses_decision` (fake LLM JSON → RouteDecision kind "sql", databases ["clinical"]), `test_route_prompt_mentions_patient_rules_in_patient_mode` (capture prompt from a fake that records inputs), `test_inject_schema_always_includes_patients`, `test_inject_schema_picks_observations_for_hba1c` ("What is my latest HbA1c?" → `observations` in schema_text), `test_extract_sql_variants` (fenced with prose; bare; trailing `;`; leading "Here is the query:"), `test_generate_sql_retry_includes_previous_error` (state with one failed attempt → prompt contains that error text), `test_timed_records_seconds`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: graph state and first pipeline nodes`.

### Task 10: validate, execute, and the retry decision

**Files:**
- Create: `backend/app/graph/nodes/validate.py`, `backend/app/graph/nodes/execute.py`, `backend/app/graph/edges.py`
- Test: `backend/tests/graph/test_validate_execute.py`, `backend/tests/graph/test_edges.py`

**Interfaces:**
- Consumes: `validate_sql`, `set_query_context`, `Deps`, `ChatState`.
- Produces: `validate(state, deps)` → on failure sets the last attempt's `error`; on success sets `final_sql` (validated SQL). `execute(state, deps)` → opens a transaction on `deps.engines[db]`, calls `set_query_context` when `engine.dialect.name == "postgresql"`, runs `final_sql`, fetches up to `rows_stored_cap + 1` rows to set `truncated`, converts values JSON-safe (date/datetime → ISO string, Decimal → float, UUID → str), drops any column whose name is a PII column name, returns `{"result": QueryResult, "sources": tables_in(...)}` with `sources` formatted `clinical_db.<table>`; DB errors → set last attempt `error` to the DB message (first line, ≤300 chars) and `result=None`. `after_validate(state) -> Literal["execute","generate_sql","fail"]` and `after_execute(state) -> Literal["synthesize","generate_sql","fail"]`: error and attempts < `max_sql_attempts` → `generate_sql`; error and attempts exhausted → `fail`; empty result is **not** an error → `synthesize`.
- Produces: `fail(state, deps)` node → `{"kind": "error", "answer": "I couldn't build a working query for that after 3 tries. Try rephrasing, or ask something more specific."}` (keeps attempts for display).

- [ ] **Step 1: Write failing tests** — edges (pure): `test_error_retries_until_limit`, `test_error_after_limit_fails`, `test_empty_result_does_not_retry` (result with 0 rows → "synthesize"). Validate (pure): `test_validate_failure_records_error`. Execute (`@pytest.mark.db`): `test_execute_returns_rows_and_sources`, `test_execute_strips_pii_columns` (bypass validator: final_sql `SELECT id, ssn FROM patients LIMIT 1` → columns == ["id"]), `test_execute_patient_mode_filters` (patient state, `SELECT count(*) FROM encounters` → equals that patient's count), `test_execute_db_error_recorded` (bad column → attempt error contains "column"), `test_execute_truncates` (cap 5 → 5 rows, truncated True).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: validated read-only execution with retry routing`.

### Task 11: synthesize and verify_numbers

**Files:**
- Create: `backend/app/graph/nodes/synthesize.py`, `backend/app/safety/number_check.py`, `backend/app/graph/nodes/verify_numbers.py`
- Test: `backend/tests/test_number_check.py`, `backend/tests/graph/test_synthesize.py`

**Interfaces:**
- Produces: `find_unverified_numbers(answer: str, rows: list[list[Any]], question: str, extra_allowed: set[float]) -> list[str]` — extracts numeric tokens from the answer (ints, decimals, with thousands separators, optional `%`, optional leading `$`); ignores digits inside Synthea-style names/ids (tokens attached to letters, e.g. `Abe604`) and ISO dates that appear verbatim in rows; a token is verified if it equals (after removing separators) any numeric cell, any number in the question, any value in `extra_allowed` (row count, total_rows), or a cell rounded to the token's shown decimal places; `%` tokens also match cell×100. Returns the original token strings that fail.
- Produces: `synthesize(state, deps)` → `{"answer", "kind": "answer"}`: if `result.total_rows == 0` returns a deterministic "No records found for that question." plus a one-line restatement — no LLM call; else LLM gets question, SQL, first `rows_to_llm` rows as a compact table, total_rows/truncated, sources; instructions: use only these numbers, mention sources, be brief, say when results are truncated. `verify_numbers(state, deps)` → runs the check; on failures re-synthesizes **once** with the offending numbers named in the prompt; if still failing returns `unverified_numbers` and appends the note "⚠ Some numbers in this answer could not be matched to the query results: …".

- [ ] **Step 1: Write failing tests** — number check: `test_exact_match`, `test_thousands_separator` ("1,234.5" vs 1234.5), `test_rounding` ("12.35" vs 12.3456), `test_percent` ("45%" vs 0.45), `test_row_count_allowed`, `test_question_numbers_allowed` ("in 2019"), `test_names_ignored` ("Abe604 has 3 visits" with 3 in rows → []), `test_invented_number_flagged` ("7" not in rows → ["7"]). Synthesize: `test_empty_result_no_llm_call` (fake LLM with zero responses would raise if called), `test_verify_resynthesizes_once` (first answer invents a number, second is clean → unverified empty), `test_verify_flags_after_second_failure`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: grounded answer synthesis with number verification`.

### Task 12: Wire the graph and the chat runner

**Files:**
- Create: `backend/app/graph/build.py`, `backend/app/graph/runner.py`
- Test: `backend/tests/graph/test_build.py`

**Interfaces:**
- Produces: `build_graph(deps: Deps) -> CompiledStateGraph`. Edges: START → route; route → (`sql` → inject_schema | `refuse` → refuse_node | `out_of_scope` → out_of_scope_node); inject_schema → generate_sql → validate → `after_validate` → execute → `after_execute` → synthesize → verify_numbers → END; fail → END. `refuse_node` returns kind "refusal" with "In patient mode I can only answer questions about your own records."; `out_of_scope_node` returns kind "out_of_scope" with a sentence naming what it can answer. (Both in `app/graph/nodes/simple_replies.py`.) In this plan route's `databases` must be `["clinical"]`; anything else → state `db="clinical"` with a note in `reason` (billing arrives in Plan 2).
- Produces: `ChatResult(BaseModel)`: `answer`, `kind`, `sql: list[SqlRecord]` (`db: DbName`, `query: str`, `error: str|None` — every attempt, so the learner sees retries), `sources`, `table: QueryResult|None`, `unverified_numbers`, `timings`. `run_chat(deps: Deps, question: str, role: str, patient_id: str|None, session_id: str) -> ChatResult` — invokes the graph; catches LLM/provider exceptions (incl. rate-limit after retries, `LLMOutputError`, connection errors) → `ChatResult(kind="error", answer="The AI service is unavailable or rate-limited right now. Please try again in a minute.")`; logs the exception.
- Produces: `build_deps(settings: Settings) -> Deps` (engines, catalog, glossary, llm) in `runner.py`.

- [ ] **Step 1: Write failing tests** — with FakeListChatModel and an in-memory SQLite engine registered as `"clinical"` (validator dialect still "postgres" — keep test SQL portable; `execute` skips `set_query_context` on SQLite by itself): `test_happy_path` (route JSON → SQL → answer containing "111" → kind "answer", sql has 1 record, sources ["clinical_db.patients"]), `test_retry_then_success` (first SQL references a missing column, second works → 2 sql records, first with error), `test_refusal_path`, `test_out_of_scope_path`, `test_llm_failure_returns_error_kind` (fake LLM raising `RuntimeError("429")`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: LangGraph pipeline wiring and chat runner`.

### Task 13: Chat, patients, and schema API

**Files:**
- Create: `backend/app/api/models.py`, `backend/app/api/chat.py`, `backend/app/api/catalog_routes.py`
- Modify: `backend/app/main.py` (include routers; build `Deps` once in lifespan, store on `app.state.deps`; dependency `get_deps(request) -> Deps`)
- Test: `backend/tests/test_api_chat.py`

**Interfaces:**
- Produces: `POST /api/chat` body `ChatRequest`: `message: str` (1–1000 chars), `role: Literal["clinician","patient"]`, `patient_id: str|None`, `session_id: str` (default new uuid4) → `ChatResult` JSON. 422 if role is patient and `patient_id` missing or not an existing patient id (lookup via clinician context). `GET /api/patients` → `[{"id", "name", "birthdate", "gender"}]` sorted by name (no PII). `GET /api/schema?db=clinical` → `[{"table", "description", "columns": [{"name","type","description"}]}]` from the catalog (PII already absent); `db=billing` allowed.

- [ ] **Step 1: Write failing tests** (override `get_deps`/`run_chat` with fakes) — `test_chat_returns_result`, `test_patient_role_requires_patient_id` (422), `test_unknown_patient_id_rejected` (422), `test_message_length_validated`, `test_patients_list_has_no_pii` (keys exactly id/name/birthdate/gender), `test_schema_endpoint_no_pii`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: chat, patients and schema endpoints`.

### Task 14: Live smoke script and the plain-language explainer

**Files:**
- Create: `backend/scripts/ask.py`, `docs/how-it-works.md`

**Interfaces:**
- Produces: CLI `python -m scripts.ask "question" [--role patient --patient-id <id>]` printing the answer, each SQL attempt (with errors), sources, and per-node timings.
- Produces: `docs/how-it-works.md` for a non-technical reader: what Aether is; the fake-patient data and why it's fake; the two databases and what lives where (simple table); what happens when you ask a question — one real question traced through route → schema → write SQL → safety check → privacy filter → run → retry → answer → number check, each with a librarian-style analogy and the actual SQL/answer captured from the smoke run; doctor vs patient view and the three privacy layers; why a cloud AI and why that's OK only with fake data; a short glossary (database, SQL, LLM, schema, RLS, API). Mark sections still to come (second database, documents, memory) as "coming next".

- [ ] **Step 1: Run** the full test suite `python -m pytest -v` → all pass (db tests pass with DBs up).
- [ ] **Step 2: Start** `uvicorn app.main:app --reload`; run `python -m scripts.ask` with: "How many patients are in the system?" (expect 111), "Which 5 conditions are most common?" (clinician), "What medications am I currently taking?" (patient), "How many patients have diabetes?" (patient → refusal), "What's the weather today?" (out_of_scope). Record outputs and timings.
- [ ] **Step 3: Write** `docs/how-it-works.md` using the recorded run.
- [ ] **Step 4: Commit** `docs: plain-language explainer and smoke script`.
