# Plan 2 — Second Database + Cross-Database Questions (Milestone 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer questions from MySQL `billing_db` and questions that need BOTH databases ("which doctor saw the most patients, by name?"), with patient privacy enforced in MySQL by a sqlglot rewrite, population columns hidden from patients, and Postgres RLS hardened with a signed identity.

**Architecture:** `route` picks the database(s). A new `plan` step turns a two-database question into two ordered sub-questions joined by a known link (e.g. `encounters.provider = providers.id`). Each step runs the existing loop (inject_schema → generate_sql → validate → **row_filter** → execute, ≤3 tries per step). `row_filter` rewrites table references into filtered derived tables: in patient mode for MySQL patient tables, and in step 2 to keep only rows matching step 1's ids (ids inserted by code, never by the AI). `merge` joins the two results in Python on the link, then synthesize/verify_numbers run as before.

**Tech Stack:** unchanged from Plan 1 (FastAPI, LangGraph 1.2, SQLAlchemy 2.1, psycopg 3, PyMySQL, sqlglot 30, pytest). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-17-healthcare-multidb-chatbot-design.md` (§8 roles/protection, §9 plan/row_filter/merge nodes, §12 tests, §15 milestone 3).

## Global Constraints

- Everything from Plan 1's Global Constraints still holds (backend/ layout, secrets only in `backend/.env`, chatbot connects as `chatbot_ro`, PII columns never shown, tests never call a real LLM, `@pytest.mark.db` tests skip when a DB is down).
- MySQL patient-bearing tables, filtered in patient mode by rewrite (from `PATIENT_COLUMN`): `claims.patientid`, `claims_transactions.patientid`, `payer_transitions.patient`. Reference tables (`providers`, `organizations`, `payers`) are not row-filtered.
- Patient-hidden population columns (spec §8, exact): `payers.amount_covered, amount_uncovered, revenue, covered_encounters, uncovered_encounters, covered_medications, uncovered_medications, covered_procedures, uncovered_procedures, covered_immunizations, uncovered_immunizations, unique_customers, qols_avg, member_months`; `organizations.revenue, utilization`; `providers.encounters, procedures`. Hidden from the schema text and rejected by the validator in patient mode only.
- Cross-database links (exact, clinical side first): `encounters.provider = providers.id`, `encounters.organization = organizations.id`, `encounters.payer = payers.id`, `medications.payer = payers.id`, `patients.id = claims.patientid`, `patients.id = payer_transitions.patient`, `patients.id = claims_transactions.patientid`.
- Ids passed between steps or used for patient filtering are inserted by code as sqlglot string literals, only after matching `^[A-Za-z0-9_.:-]{1,64}$` (anything else raises). This replaces driver parameters because the raw cursor runs without parameters so `%` in `LIKE` stays literal (Plan 1 design).
- Cross-database plans have at most 2 steps and exactly one link.
- Every new node has a plain-English docstring; `docs/how-it-works.md` is updated in the last task.

## Review Focus

1. **Patient reads population totals through reference tables:** `SELECT sum(amount_covered) FROM payers` or `SELECT * FROM organizations` in patient mode must be rejected; clinicians are unaffected. → Task 1 `test_patient_mode_blocks_population_columns`.
2. **MySQL row-filter bypass:** claims reached via alias, subquery, CTE, UNION, JOIN, `billing_db.claims`, or a CTE named `claims` must all be filtered. → Task 2 tests, plus the real-MySQL attack list in Task 7.
3. **Mid-query identity switch in Postgres:** SQL that calls `set_config('app.role','clinician')` partway through a query (if the validator ever let it through) must see no extra rows. → Task 3 `test_forged_role_mid_query_sees_nothing`.
4. **Step 1 finds nothing:** a cross-database question whose first step returns zero rows must answer "No records found" and never run step 2 with an empty filter. → Task 6 `test_cross_db_empty_first_step`.
5. **Hostile or odd ids between steps:** an id containing a quote, or more than 1,000 ids, must not produce broken or injected SQL. → Task 2 `test_rejects_unsafe_values`, `test_many_values`.

---

### Task 1: Glossary links, patient-hidden columns, role-aware schema and validator

**Files:**
- Modify: `backend/app/semantic/glossary.yaml`, `backend/app/semantic/glossary.py`, `backend/app/db/catalog.py` (`render`), `backend/app/graph/nodes/validate.py`
- Test: `backend/tests/test_glossary.py`, `backend/tests/test_catalog.py`, `backend/tests/graph/test_validate_execute.py`

**Interfaces:**
- Produces: `Glossary.links: list[str]` (the 7 links above, "a.b = c.d"), `Glossary.patient_hidden_columns: list[str]` ("table.column"), `Glossary.blocked_columns(role: str) -> set[str]` (PII always; plus hidden columns when role == "patient"). `Catalog.render(table_names: list[str], hidden: set[str] = frozenset()) -> str` skips columns whose "table.column" is in `hidden`.
- `validate` uses `deps.glossary.blocked_columns(state["role"])`.

- [ ] **Step 1: Failing tests:** `test_links_loaded` (7 links; `"encounters.provider = providers.id"` present); `test_blocked_columns_by_role` (clinician == the 3 PII columns; patient ⊇ PII ∪ {"payers.revenue", "providers.encounters"}); `test_render_hides_columns` (render(["patients"], hidden={"patients.gender"}) has no "gender"); `test_patient_mode_blocks_population_columns` (validate node, db billing, catalog containing payers/organizations: patient + `SELECT sum(amount_covered) FROM payers` → error; patient + `SELECT * FROM organizations` → error; patient + `SELECT name, phone FROM payers` → ok; clinician + the sum → ok). Extend `tests/fakes.small_catalog()` with billing tables `providers(id,name,speciality,organization,encounters,procedures)`, `organizations(id,name,city,revenue,utilization)`, `payers(id,name,amount_covered,revenue,unique_customers)`, `claims(id,patientid,providerid,outstandingp,servicedate)` with db "billing".
- [ ] **Step 2: Run** `python -m pytest tests/test_glossary.py tests/test_catalog.py tests/graph/test_validate_execute.py -q` → new tests FAIL.
- [ ] **Step 3: Implement** (YAML lists + model fields + method; `render` filter; validate change). Also replace the old free-text `join_keys` cross-database comments so `links` is the single source for cross-DB joins (keep `join_keys` for same-database joins only).
- [ ] **Step 4: Run** same command → PASS; full `python -m pytest -q` → all pass.

### Task 2: The row-filter rewrite (pure sqlglot function)

**Files:**
- Create: `backend/app/safety/row_filter.py`
- Test: `backend/tests/test_row_filter.py`

**Interfaces:**
- Produces: `class RowFilter(NamedTuple): table: str; column: str; values: list[str]`; `restrict_tables(sql: str, dialect: Dialect, filters: list[RowFilter]) -> str`. Every real reference (CTE names excluded, via `sql_validator._real_tables`) to a filtered table, at any depth, becomes `(SELECT * FROM <same schema.table> WHERE <cond>) AS <original alias or table name>`. `<cond>` = `column = 'v'` for one value, `column IN (...)` for several, `FALSE` (`1 = 0`) for none; several filters on one table are ANDed. Values are deduplicated, and any value not matching `SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")` raises `ValueError`. Tables not referenced are ignored. Returns `tree.sql(dialect=dialect)`.
- Also produces `UnsafeValueError(ValueError)`.

- [ ] **Step 1: Failing tests** (dialect "mysql", filter `RowFilter("claims", "patientid", ["p1"])`; each asserts by executing the rewritten SQL on an in-memory SQLite db with `claims` rows for p1 and p2, so the check is "only p1 rows come back", not string matching): `test_plain_reference`, `test_alias_kept` (`FROM claims c WHERE c.outstandingp > 0`), `test_subquery` (`WHERE x IN (SELECT id FROM claims)`), `test_cte_body` (`WITH t AS (SELECT * FROM claims) SELECT count(*) FROM t`), `test_cte_named_like_table` (`WITH claims AS (SELECT * FROM claims) SELECT count(*) FROM claims` → 1 row counted for p1 only), `test_union` (both branches filtered), `test_join_two_filtered_tables` (claims + claims_transactions filters both applied), `test_schema_qualified` (`billing_db.claims` → inner select keeps `billing_db.claims`; assert via sqlglot that the inner WHERE exists), `test_multiple_values_in_list`, `test_no_values_returns_nothing`, `test_two_filters_same_table_are_anded`, `test_rejects_unsafe_values` (`"x' OR '1'='1"` → UnsafeValueError), `test_many_values` (1,500 ids → valid SQL, executes), `test_unreferenced_table_unchanged`.
- [ ] **Step 2: Run** `python -m pytest tests/test_row_filter.py -q` → FAIL (module missing).
- [ ] **Step 3: Implement** `row_filter.py`. Collect targets first (`_real_tables`), then `table.replace(subquery)`, so inner derived tables are never rewritten again.
- [ ] **Step 4: Run** → PASS.

### Task 3: Signed identity for PostgreSQL row-level security (defense in depth)

Plain idea: today the RLS policy trusts the notes `app.role` / `app.patient_id`. If a future validator hole let SQL call `set_config`, a patient could rewrite those notes. Now the app also writes `app.sig` = SHA-256 of `key|role|patient_id`, where the key sits in a table `chatbot_ro` cannot read. The policy re-checks the signature on every row via a SECURITY DEFINER function, so changed notes stop matching and show nothing. Measured cost: ~5 µs per row (+0.27 s on a full 54k-row observations scan as clinician); patient mode is still pre-filtered by the indexed plain condition.

**Files:**
- Modify: `backend/app/config.py` (field `rls_secret: str = ""`, method `rls_key() -> str` = `rls_secret` or `sha256("aether-rls|" + pg_admin_password)` hex), `backend/app/db/rls.py`, `backend/scripts/sql/postgres_rls.sql`, `backend/scripts/setup_databases.py` (new `--rls-only` flag), `backend/.env.example` (`RLS_SECRET=` with comment "optional; derived from PG admin password if empty"), `docs/setup-windows.md` (rerun `--rls-only` after changing the PG admin password or RLS_SECRET)
- Create: `backend/scripts/sql/postgres_identity.sql`
- Test: `backend/tests/test_rls.py`, `backend/tests/test_config.py`, `backend/tests/test_setup_helpers.py`

**Interfaces:**
- Produces: `rls.identity_signature(key: str, role: str, patient_id: str | None) -> str` (hex sha256 of `f"{key}|{role}|{patient_id or ''}"`); `set_query_context(conn, role, patient_id)` unchanged signature, now also sets `app.sig` (key from `get_settings().rls_key()`).
- SQL objects: schema `aether_private` (USAGE to chatbot_ro only), table `aether_private.rls_key(k text)` (no grant to chatbot_ro), function `aether_private.identity_ok() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog` (compares `app.sig` with the recomputed hash; false when unset), EXECUTE granted to chatbot_ro only. Policy becomes `USING ((current_setting('app.role', true) = 'clinician' OR {patient_col} = current_setting('app.patient_id', true)) AND aether_private.identity_ok())` — not wrapped in a sub-select, so it is evaluated per row.
- `apply_postgres_rls(pg, key: str)`: runs `postgres_identity.sql` (key as bind parameter `:key`), then the per-table template. Idempotent.

- [ ] **Step 1: Failing tests:** `test_identity_signature_stable` (known input → known hex); `test_rls_key_derived_when_unset` / `test_rls_key_explicit` (config); db tests in `test_rls.py` (use real clinical DB, `chatbot_ro`): `test_correct_context_still_works` (patient sees 1 patient row; clinician sees all), `test_unsigned_context_sees_nothing` (set app.role='clinician' via raw `set_config` without sig → count 0), `test_forged_role_mid_query_sees_nothing` (after a correct patient context, run `SELECT count(*) FROM patients WHERE set_config('app.role','clinician',true) IS NOT NULL` directly on the connection → ≤ 1), `test_ro_cannot_read_key` (`SELECT k FROM aether_private.rls_key` as chatbot_ro → permission error).
- [ ] **Step 2: Run** `python -m pytest tests/test_rls.py tests/test_config.py -q` → new tests FAIL.
- [ ] **Step 3: Implement**, then run `python scripts/setup_databases.py --rls-only` (applies identity + policies only; no data reload) against the local DBs.
- [ ] **Step 4: Run** the same tests → PASS; full suite (including `tests/test_patient_isolation.py`) → PASS.

### Task 4: Routing to both databases and the `plan` step

**Files:**
- Modify: `backend/app/graph/state.py`, `backend/app/graph/nodes/route.py` (remove the Plan 1 clinical-only override; empty `databases` on an sql route → `["clinical"]`), `backend/app/llm/prompts.py`
- Create: `backend/app/graph/nodes/plan.py`
- Test: `backend/tests/graph/test_plan.py`, `backend/tests/graph/test_first_nodes.py`

**Interfaces:**
- Produces (state.py): `PlanStep(BaseModel): db: DbName; goal: str`; `Link(BaseModel): from_table, from_column, to_table, to_column: str` (from = step 1's side); `QueryPlan(BaseModel): steps: list[PlanStep]; link: str | None = None` (the AI's raw JSON shape); `StepResult(BaseModel): db: DbName; sql: str; result: QueryResult; sources: list[str]`. New ChatState keys: `plan: list[PlanStep]`, `link: Link | None`, `step: int`, `step_results: list[StepResult]`. Attempt dicts gain `step: int`, `db: DbName`, `executed: str | None`. `merge_dicts` now SUMS repeated keys (a node that runs once per step reports total time).
- Produces (prompts.py): `DATABASES_DESCRIPTION` gains a `billing` line (MySQL billing_db: organizations, providers/doctors with names and specialities, payers/insurers, payer_transitions, claims, claims_transactions); `plan_system(links: list[str]) -> str`; `sql_system(dialect_name, role)` adds per-dialect notes (MySQL: no ILIKE — use LIKE, which is case-insensitive; LIMIT; date functions `DATE_FORMAT`, `YEAR()`; PostgreSQL: ILIKE allowed).
- Produces (plan.py): `normalize_plan(raw: QueryPlan, databases: list[DbName], glossary: Glossary, catalog: Catalog) -> tuple[list[PlanStep], Link | None]` (raises `LLMOutputError` when: 2 steps on the same db, >2 steps, link missing or not in `glossary.links`, or neither link side belongs to step 1's db; orients the link so `from_*` is step 1's side) and node `plan(state, deps) -> {"plan", "link", "step": 0, "db": steps[0].db, "step_results": []}`. One database → one step with `goal = question`, **no AI call**.

- [ ] **Step 1: Failing tests:** `test_single_db_no_llm_call` (ScriptedLLM with no replies; route databases ["billing"] → plan == [PlanStep("billing", question)], link None); `test_two_db_plan` (scripted JSON `{"steps":[{"db":"clinical","goal":"count distinct patients per provider id"},{"db":"billing","goal":"provider names"}],"link":"encounters.provider = providers.id"}` → Link(encounters, provider, providers, id)); `test_link_oriented_to_first_step` (steps billing→clinical with same link string → from_table "providers", to_table "encounters"); `test_unknown_link_rejected`, `test_same_db_twice_rejected`; `test_route_keeps_billing` (route reply databases ["billing"] stays ["billing"]); `test_merge_dicts_sums`.
- [ ] **Step 2: Run** `python -m pytest tests/graph -q` → new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS (graph wiring comes in Task 6; existing tests stay green).

### Task 5: Per-step SQL loop — schema, generation, row_filter, execute key check

**Files:**
- Modify: `backend/app/graph/nodes/inject_schema.py`, `generate_sql.py`, `validate.py`, `execute.py`, `backend/app/graph/edges.py`, `backend/app/llm/prompts.py` (`sql_user` gets `notes: list[str] = ()`)
- Create: `backend/app/graph/nodes/row_filter.py`
- Test: `backend/tests/graph/test_steps.py`

**Interfaces:**
- inject_schema: scores against `plan[step].goal` within `plan[step].db` only; force-includes the link table of this step's side; passes `hidden = glossary.blocked_columns(role) - pii` to `render` (PII is already absent from the catalog).
- generate_sql: dialect from `state["db"]`; question text = `"Overall question: <q>\nThis step: <goal>"` when the plan has 2 steps, else the question; only this step's attempts are shown as "previous"; link notes — step 0: "Include the column {from_table}.{from_column} in the output, unaliased: the next step uses it to look up {to_table} in {other_db}."; step 1: "Code will automatically keep only {to_table} rows whose {to_column} is one of the {n} values found in step 1. Do not filter on {to_column} yourself. Include {to_table}.{to_column} unaliased if you return one row per item; for an overall total you may aggregate." Appends `{"step", "db", "sql", "executed": None, "error": None}`.
- row_filter node `row_filter(state, deps) -> dict`: filters = patient mode on billing → `RowFilter(t, PATIENT_COLUMN[t], [patient_id])` for each billing table in PATIENT_COLUMN; step 1 with a link → `RowFilter(to_table, to_column, distinct non-null str values of from_column in step_results[0].result)`. If the link table is not read by the query → attempt error "Use the table {to_table} in this query." `UnsafeValueError`/parse errors → attempt error. On success sets `final_sql` to the rewritten SQL and `attempts[-1]["executed"]` when it changed.
- execute: on step 0 with a link, if `from_column` is not among result columns (case-insensitive) → attempt error "Include the column {from_column} in the output (unaliased)…" (counts as a failed try).
- edges: tries counted per current step (`a["step"] == state["step"]`); `after_validate` → `row_filter | generate_sql | fail`; new `after_row_filter` → `execute | generate_sql | fail`; `after_execute` → `next_step | generate_sql | fail`.

- [ ] **Step 1: Failing tests** (fake deps + SQLite engines named "clinical" and "billing"): `test_schema_uses_step_db_and_goal` (billing step → "TABLE providers" present, "TABLE patients" absent); `test_patient_schema_hides_population_columns`; `test_step1_notes_in_prompt` / `test_step2_notes_in_prompt` (ScriptedLLM.prompt_text contains the link wording); `test_row_filter_patient_billing` (patient + `SELECT sum(outstandingp) FROM claims` → executed SQL contains `patientid = 'p1'`, executes to p1's total only); `test_row_filter_clinician_billing_unchanged` (executed stays None); `test_row_filter_link_values` (step_results[0] rows with provider ids → `id IN ('a', 'b')`); `test_row_filter_missing_link_table_is_error`; `test_missing_key_column_is_error`; `test_retries_counted_per_step` (2 failed tries in step 0 + 1 in step 1 → still allowed to retry step 1).
- [ ] **Step 2: Run** `python -m pytest tests/graph/test_steps.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.

### Task 6: next_step, merge, graph wiring, runner and answer

**Files:**
- Create: `backend/app/graph/nodes/merge.py`
- Modify: `backend/app/graph/build.py` (new flow + updated ASCII diagram), `backend/app/graph/edges.py` (`after_next_step`), `backend/app/graph/runner.py`, `backend/app/graph/nodes/synthesize.py`, `backend/app/graph/nodes/simple_replies.py` (out_of_scope text mentions doctors, hospitals, insurers and claims)
- Test: `backend/tests/graph/test_merge.py`, `backend/tests/graph/test_build.py`

**Interfaces:**
- Flow: `route → plan → inject_schema → generate_sql → validate → row_filter → execute → next_step → (inject_schema if another step and the last result is non-empty, else merge) → synthesize → verify_numbers`.
- `next_step(state, deps)`: appends `StepResult(db, final_sql, result, sources)`; increments `step`; when another step follows, sets `db` to its db and clears `final_sql`/`result`.
- `merge_results(left: QueryResult, right: QueryResult, left_key: str, right_key: str, cap: int) -> QueryResult` (pure): left join in left-row order; matching is case-insensitive on column names; right's key column dropped; name clashes on the right get suffix `_2`; `truncated` = either input truncated or the cap was hit. If `right_key` is not in right's columns → right returned unchanged (step 2 aggregated over the filtered rows).
- `merge(state, deps)`: one result → that result; two → `merge_results`; sources = union in step order. Sets `result` and `sources`.
- runner: `SqlRecord(db=a["db"], query=a["executed"] or a["sql"], error=a["error"])`. synthesize shows every step's SQL ("SQL that ran:" block per step with its database).

- [ ] **Step 1: Failing tests:** merge unit tests — `test_left_join_keeps_left_order`, `test_unmatched_left_rows_get_nulls`, `test_clash_suffix`, `test_right_without_key_is_returned`, `test_cap_and_truncation`. Graph tests (two SQLite engines: clinical `encounters(id, patient, provider)`, billing `providers(id, name)`, `claims(id, patientid, outstandingp)`) — `test_billing_only_question` (route billing → one step, answer, sources ["billing_db.providers"]); `test_cross_db_doctor_name` (scripted route both dbs → plan JSON → step-1 SQL `SELECT provider, count(DISTINCT patient) AS n FROM encounters GROUP BY provider ORDER BY n DESC LIMIT 1` → step-2 SQL `SELECT id, name FROM providers` → answer containing the doctor's name; asserts result.sql has 2 records with dbs [clinical, billing], the second's query contains `IN (`/`=` with the top provider id, merged table columns `["provider", "n", "name"]`, sources contain both dbs); `test_cross_db_empty_first_step` (step 1 returns 0 rows → "No records found", only 1 SQL record, no step-2 AI call); `test_patient_billing_filtered` (patient p1, claims for p1+p2 → total equals p1's only); existing 4 tests still pass (update `ROUTE_SQL` usage only if needed).
- [ ] **Step 2: Run** `python -m pytest tests/graph -q` → new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** full `python -m pytest -q` → all PASS.

### Task 7: Real-database privacy regression, live check, docs

**Files:**
- Modify: `backend/tests/test_patient_isolation.py` (add MySQL), `docs/how-it-works.md`, `backend/app/llm/prompts.py` / `glossary.yaml` only if the live check exposes a wording problem (each such change gets a unit test first)
- Test: `backend/tests/test_patient_isolation.py`

**Interfaces:** consumes everything above; produces no new code API.

- [ ] **Step 1: Add the MySQL attack list** (patient mode, run through real `validate → row_filter → execute` against `billing_db` as `chatbot_ro`; assert no `patientid` other than the patient's appears and counts never exceed the patient's own count from an admin query): `SELECT count(*) FROM claims`, `SELECT count(*) FROM claims WHERE 1=1 OR patientid IS NOT NULL`, `SELECT patientid FROM claims UNION SELECT patientid FROM claims_transactions`, `SELECT c.patientid FROM claims c JOIN claims_transactions t ON t.claimid = c.id`, `WITH claims AS (SELECT * FROM billing_db.claims) SELECT DISTINCT patientid FROM claims`, `SELECT DISTINCT patient FROM payer_transitions`, `SELECT (SELECT count(*) FROM claims) AS n`, `SELECT sum(amount_covered) FROM payers` (must be rejected). Plus a cross-DB case: step-2 link values that include another patient's id are still ANDed with the patient filter.
- [ ] **Step 2: Run** `python -m pytest tests/test_patient_isolation.py -q` → PASS (these are regression guards over Tasks 1–5; if one fails, it is a bug in those tasks: fix it test-first).
- [ ] **Step 3: Live check** with the real LLM via the scratch eval script (not committed): B1 "Which insurance company has the most customers?", B2 "How many hospitals or clinics are in Boston?", X1 "Which doctor has seen the most patients? Give the doctor's name.", X2 "What is the total outstanding patient balance for patients with diabetes?", P6 (patient) "How much do I still owe?", P7 (patient) "What is the total revenue of my insurer?" (must refuse or omit revenue), and the Plan 1 cases again (no regressions). Ground truth from admin SQL. Record the results.
- [ ] **Step 4: Update `docs/how-it-works.md`** for a non-technical reader: the second database and what lives where; the "plan" step with the traced X1 example (both SQL queries, how ids pass between them, the merged table); MySQL's privacy rewrite vs Postgres RLS (with the before/after SQL); the signed note (why a forged note shows nothing); hidden population numbers for patients; updated pipeline flowchart and report card; glossary entries (derived table, merge, signature).
- [ ] **Step 5: Full suite** `python -m pytest -q` → all PASS.
