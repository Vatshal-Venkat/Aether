# Aether — Healthcare Multi-Database Chatbot (Backend) — Design

**Date:** 2026-11-17
**Status:** Draft, awaiting approval
**Source material:** `Building a Multi-Database Chatbot (Structured Data Query + RAG) – 2026.pdf` (the "PDF")

## 1. Intent and why

A learning ("prep-up") project. The owner wants to understand, end to end, how a chatbot answers
plain-English questions by finding the right database(s), writing safe SQL, running it, combining
results across databases, and searching documents (RAG) — and to be able to measure how well it works.

It is not going to be deployed. Everything must be **free and open source** and run on the owner's
Windows laptop (Ryzen 5 7235HS, 24 GB RAM, RTX 3050 6 GB, Python 3.13, Node installed; Docker not installed).

This phase is the **backend only** (FastAPI). A React frontend comes later and will consume the API
defined here. A plain-language explainer document is a first-class deliverable alongside the code.

## 2. Goals

1. Answer healthcare questions using two live databases and a document store:
   - **PostgreSQL `clinical_db`** — the medical record.
   - **MySQL `billing_db`** — providers, organizations, insurers, claims.
   - **ChromaDB** — FDA drug-label text for the RAG path.
2. Implement every backend topic in the PDF: routing, schema injection, text-to-SQL, SQL validation,
   self-correction, cross-DB merge, RAG and hybrid questions, semantic glossary, row-level security,
   PII exclusion, audit logging, caching, timeouts, pagination, concurrency limits, streaming,
   clarification / out-of-scope handling, conversation follow-ups, citations, health + metrics, testing and evaluation.
3. Two roles, selected per request with no authentication ("view as"):
   - **Clinician** — may see all patients.
   - **Patient** — may see only their own records (plus non-personal reference data and drug labels).
4. An evaluation harness that produces numbers: routing accuracy, answer accuracy, per-step latency, retry counts.
5. `docs/how-it-works.md`: an explainer a non-technical person can follow, updated as each milestone lands.

## 3. Non-goals (this phase)

- Login / authentication / API keys. Role is a request field. (Owner will ask if needed later.)
- Deployment, Docker, Kubernetes, HTTPS.
- Frontend (later phase; the API must be frontend-ready: CORS for localhost, streaming endpoint, patient list endpoint).
- Trino / federation engine. Planned as an optional **later** comparison mode, not part of this build.
- Real patient data. Synthetic (Synthea) only.
- Any write to the data databases. Web scraping.

## 4. Anti-goals (failure even if it "works")

- Patient mode returning **any** other patient's data — directly, via aggregates, or via a crafted prompt.
- Numbers in an answer that did not come from query results (hallucinated data). If no rows, say so.
- SSN, driver's licence or passport columns ever reaching the LLM or the response.
- Opaque answers: every data answer must show the SQL run and its sources (database + table).
- Code so wrapped in framework magic that the owner can't follow it. Each graph node is a small,
  commented Python function; LangGraph only wires them.

## 5. Constraints

- $0 spend. Software is open source; the **LLM is a free-tier cloud API** for speed (owner's decision, 2026-11-17):
  - **Default: Groq** (free tier, hosts open-weight models such as gpt-oss-120b / Llama / Qwen; very fast).
  - **Alternative: Google Gemini** free tier (Flash models). Free-tier daily limits were reported cut sharply in 2025–26, so not the default.
  - **Offline fallback: Ollama** with a ~7B local model (fits 6 GB VRAM) — optional install.
  - The provider is a setting in `.env`; the code talks to a single LLM interface (LangChain chat-model adapters:
    `langchain-groq`, `langchain-google-genai`, `langchain-ollama`). The eval harness can compare providers.
  - Free tiers rate-limit (requests/tokens per minute and per day): the client must back off and retry on HTTP 429, and
    can fall back to the next configured provider. Keep prompts lean (schema injection already limits tokens).
  - Data sent to these APIs is synthetic (Synthea), so this is acceptable here. The explainer must note that real patient
    data could never be sent to a free tier (no HIPAA business-associate agreement; free-tier prompts may be used by the provider).
- Embeddings for RAG run locally (Chroma's built-in small ONNX embedding model, CPU), so document search needs no API calls.
- Windows, native installs (no Docker): PostgreSQL 18 (EDB installer), MySQL 8.4 LTS (MSI). The owner installs these
  and Ollama; the project provides step-by-step instructions.
- Secrets (DB admin and read-only passwords) live in `backend/.env` (git-ignored); `.env.example` committed.
- Local small models make SQL mistakes → validation and the self-correction loop are essential, not optional.

## 6. Approaches considered

| | Approach | Trade-off | Decision |
|---|---|---|---|
| A | Hand-written pipeline in plain Python, middleware merge | Most transparent; more plumbing code | Not chosen |
| **B** | **Same pipeline steps as hand-written nodes, wired with LangGraph** | Retry loop, branching and conversation memory handled by the framework; industry-relevant skill; slightly more abstraction | **Chosen by owner** — wants LangGraph *and* to understand it, hence the explainer doc and commented nodes |
| C | Trino federation engine; LLM writes one SQL across both DBs | "True" federation; heavy (Java, RAM next to the LLM), fiddly on Windows without Docker; Trino connects as one user so Postgres RLS can't see who's asking | Deferred as a later optional comparison mode |

**Federation vs virtualization:** we use **federation** (query each live database in place, merge in the
middleware — the PDF's "middleware merge") plus a **lightweight semantic layer** (`glossary.yaml`), which is the
core idea of virtualization (one consistent vocabulary and join map over many sources) without a heavy tool.

## 7. Data

**Source:** Synthea synthetic patients, pre-generated CSV
(`https://synthetichealth.github.io/synthea-sample-data/downloads/latest/synthea_sample_data_csv_latest.zip`, ~5 MB,
verified 2026-11-17). Contents: 111 patients, ~180k rows across 18 CSVs. All files share patient IDs.

**Split:**

| Database | Tables |
|---|---|
| PostgreSQL `clinical_db` | patients, encounters, conditions, observations, medications, procedures, immunizations, allergies, careplans, devices, imaging_studies, supplies |
| MySQL `billing_db` | organizations, providers, payers, payer_transitions, claims, claims_transactions |
| ChromaDB `drug_labels` | openFDA label sections (indications, warnings, adverse reactions, dosage, contraindications) for the medications present in `medications` |

Natural cross-DB links: `encounters.provider → providers.id`, `encounters.organization → organizations.id`,
`encounters.payer → payers.id`, `patient → claims.patientid`.

**Loading conventions:** column names lower-cased (Synthea ships upper case; lower case avoids Postgres quoting
problems for the LLM). Sensible types (dates, numerics) and primary/indexed keys on id / patient columns.

**Drug labels:** fetched via the free openFDA label API (no key needed at this volume) for the distinct medications
in `medications`, matched by RxNorm code (`medications.code`) with a generic-name fallback. Chunked by label section,
embedded locally, stored in ChromaDB with metadata (drug, section, source URL). Check openFDA terms of use before fetching.

**Sensitive columns** (`patients.ssn`, `drivers`, `passport`): excluded from the schema shown to the LLM and blocked by
the SQL validator for both roles.

**Authoritative sources (glossary rule):** cost appears in both DBs (`encounters.total_claim_cost`, `medications.totalcost`
in clinical; `claims_transactions` in billing). Glossary defines which source answers which money question
(e.g. "what insurance paid / what I owe" → billing_db claims; "visit cost" → encounters) so answers are consistent.

## 8. Roles and data protection

Role arrives on every request: `role: "clinician"` or `role: "patient"` + `patient_id`. No passwords.

Three layers:
1. **Read-only DB accounts** (`chatbot_ro` in each DB), SELECT only on the chatbot's tables. Admin credentials are used
   only by the setup script.
2. **Row filtering for patient mode** — deliberately two techniques, to teach both:
   - **PostgreSQL: native Row-Level Security.** Policies on every patient-bearing table compare the row's patient to a
     per-transaction setting (e.g. `app.patient_id`); clinician mode sets a role flag that the policy allows through.
     `chatbot_ro` is not the table owner (RLS doesn't apply to owners).
   - **MySQL: middleware rewrite with sqlglot.** MySQL has no RLS. Before execution, every reference to a
     patient-bearing table (`claims`, `claims_transactions`, `payer_transitions`) is replaced with a filtered derived
     table (`(SELECT * FROM claims WHERE patientid = :pid) AS claims`), including inside subqueries/CTEs, with the ID
     bound as a parameter. Reference tables (providers, organizations, payers) stay unfiltered.
3. **Audit log** — every request: timestamp, role, patient_id, question, route decision, each SQL statement + database,
   row counts, status, latency.

**Population-statistic columns hidden in patient mode:** the Synthea reference tables carry totals computed across all
patients — `payers` (amount_covered, amount_uncovered, revenue, covered_*/uncovered_* counts, unique_customers, qols_avg,
member_months), `organizations` (revenue, utilization), `providers` (encounters, procedures). In patient mode these columns
are removed from the injected schema and blocked by the validator (a role-specific column blocklist, on top of the PII
blocklist that applies to both roles). Patients can still see names, addresses, phone numbers, specialities of their
insurers, hospitals and doctors. Clinicians see all of these columns.

**Patient-mode scope:** the router declines questions about other patients or population statistics ("How many patients
have diabetes?") with a polite refusal. RLS/rewrite is the hard guarantee if the router misses one.

## 9. Architecture

```
POST /api/chat ──► LangGraph pipeline ──► answer + SQL + sources + rows + timings
                      │
 load history ─► contextualize follow-up ─► route ─┬─► clarify / out-of-scope / refuse ─► respond
                                                   ├─► RAG: retrieve chunks ───────────────┐
                                                   └─► SQL: plan sub-queries               │
                                                         └─► for each: inject schema ─►    │
                                                             generate SQL ─► validate ─►   │
                                                             row-filter ─► execute         │
                                                             (error/empty-suspicious ─►    │
                                                              back to generate, ≤3 tries)  │
                                                         └─► merge results (by keys) ──────┤
                                                                                           ▼
                                                                  synthesize answer + citations ─► audit ─► respond
```

**Nodes (each a small, commented Python function in `graph/nodes/`):**
- **contextualize** — rewrites a follow-up ("what about last year?") into a standalone question using recent turns.
- **route** — classifies intent: `sql` (which DB(s)), `rag`, `hybrid`, `clarify`, `out_of_scope`, `refuse` (patient asking
  about others). LLM with structured output, informed by glossary keywords and a short description of each source.
- **plan** — for multi-DB questions, produce ordered sub-queries; a later step may take a previous step's results as
  input (e.g. top-5 patient IDs → claims lookup). IDs passed between steps are bound by code as parameters, never pasted by the LLM.
- **inject_schema** — selects only relevant tables/columns from a schema catalog built by introspection at startup,
  enriched with glossary descriptions; PII columns removed.
- **generate_sql** — dialect-aware (Postgres vs MySQL) prompt with schema, glossary, few-shot examples; on retry, includes the previous SQL and error.
- **validate** (sqlglot) — exactly one statement; SELECT only (AST check, no DML/DDL, no `INTO OUTFILE`, no multiple statements);
  only catalog tables; no blocked columns; adds `LIMIT` if absent; parses in the target dialect.
- **row_filter** — patient mode: MySQL rewrite as in §8; Postgres sets transaction-local settings.
- **execute** — pooled read-only connection, statement timeout (Postgres `statement_timeout`, MySQL `MAX_EXECUTION_TIME`), row cap.
- **self-correct** — conditional edge back to generate_sql on error (max 3 attempts), then a graceful failure message.
- **merge** — joins/combines sub-results in Python on declared keys; records provenance per column.
- **retrieve** (RAG) — embed question, top-k from ChromaDB; in hybrid mode, query is narrowed using SQL results
  (e.g. the patient's medication names).
- **synthesize** — LLM writes the answer **from the rows/chunks only**, with citations (`clinical_db.medications`,
  `openFDA label: metformin — Warnings`). "No records found" when empty. Conflicts between sources are stated, not hidden.
- **verify_numbers** — code check (no LLM): every number in the drafted answer must match a value in the result rows or
  retrieved chunks, or be derivable trivially (row counts, the question's own numbers), after normalizing formatting
  (thousands separators, rounding to shown precision, percentages). On a mismatch: re-synthesize once with the offending
  numbers called out; if it still fails, return the answer with `unverified_numbers` listed in the payload and a visible note.
- **audit** — writes the audit record.

**Conversation memory:** LangGraph checkpointer persisted to SQLite, keyed by `session_id`; last N turns used.

## 10. API (FastAPI)

| Endpoint | Purpose |
|---|---|
| `POST /api/chat` | Body `{session_id, message, role, patient_id?}` → `{answer, kind (answer/clarification/refusal/out_of_scope/error), sql: [{db, query}], sources, table: {columns, rows, result_id, total_rows}, timings}` |
| `POST /api/chat/stream` | Same input; Server-Sent Events: progress events live per node ("Routing…", "Querying clinical_db…", "Checking numbers…"); the answer text is streamed in chunks **after** verify_numbers passes (with a fast cloud LLM this hold-back is about a second), then the final payload. Event types: `progress`, `answer_chunk`, `final`, `error` |
| `GET /api/results/{result_id}?page=n` | Pagination of a cached large result |
| `GET /api/patients` | id + display name list for the "view as patient" picker |
| `GET /api/schema?db=` | Tables/columns/descriptions (for a schema sidebar), PII excluded |
| `GET /api/sessions/{id}` | Conversation history |
| `GET /api/audit?limit=` | Recent audit entries (learning/debug view) |
| `GET /health` | DBs, Ollama, Chroma reachable |
| `GET /metrics` | Prometheus format: request counts, latencies per node, SQL errors, retries, cache hits |

CORS allows `localhost` origins for the future React app.

## 11. Performance and robustness

- Connection pools per DB; statement timeouts; result row cap (e.g. 1000 stored, 50 sent to the LLM, 100 per page).
- Free-tier LLM limits → a concurrency limit (semaphore) and client-side pacing on LLM calls, 429 back-off/retry,
  provider fallback; simple per-IP request rate limit on our own API.
- Cache: LRU with TTL keyed on (normalized standalone question, role, patient_id, schema version).
- Transient DB errors retried once; permanent errors go to self-correction or fail gracefully.
- Startup checks with clear messages when a DB/Ollama is down.

## 12. Testing and evaluation

- **Unit tests (pytest):** validator (blocks DML/DDL, multi-statements, PII columns, unknown tables), MySQL row-filter rewrite
  (incl. subqueries, CTEs, aliases, joins), merge logic, glossary loading.
- **Security tests against the real DBs:** patient mode cannot read other patients through either DB, including adversarial
  SQL (`OR 1=1`, UNION, subqueries) fed straight to validate → row_filter → execute.
- **Graph tests** with a fake LLM returning canned outputs, so pipeline logic is tested deterministically.
- **Evaluation harness** (`scripts/run_eval.py`): ~40 questions in YAML, each with role, category
  (single-DB clinical, single-DB billing, cross-DB, RAG, hybrid, clarify, out-of-scope, patient-refusal), expected route,
  and gold SQL / expected answer. Report: routing accuracy, execution accuracy (result-set match), refusal correctness,
  per-node latency (p50/p95), retries, LLM calls and tokens per question, unverified-number rate. Saved as a dated markdown
  report so runs can be compared over time, across LLM providers, and later vs Trino.
- **Scoring by category:** SQL questions → execution accuracy (result-set match vs gold SQL, order-insensitive unless the
  question asks for an order). RAG and hybrid questions → each has a short list of expected facts (keywords/values) that the
  answer must contain, plus the expected source label; scored deterministically by code (no LLM judge, so it doesn't spend
  free-tier quota and is repeatable). Clarify / out-of-scope / refusal → expected `kind`.
- **The eval measures; it does not gate milestones.** Informal targets to aim for, not pass/fail: typical answer under
  ~10 s on Groq; routing ≥ 90%; SQL execution accuracy ≥ 75%; zero patient-data leaks (this one *is* a hard requirement,
  enforced by the security tests, not the eval).

## 13. Tech stack (all free / open source)

FastAPI + Uvicorn; LangGraph (+ SQLite checkpointer); LLM via langchain-groq (default), langchain-google-genai,
langchain-ollama (offline fallback; ~7B model, builder picks what fits 6 GB); local embeddings via ChromaDB's default
ONNX model; SQLAlchemy 2 + psycopg 3 + PyMySQL; sqlglot; ChromaDB; pandas (merge); httpx (openFDA);
prometheus-client; pytest; pydantic-settings. App-side state (audit log, cache metadata, sessions) in SQLite.

## 14. Project layout

```
backend/
  app/
    main.py            FastAPI app, routes
    config.py          settings from .env
    api/               request/response models, routers
    graph/             state.py, build.py (LangGraph wiring), nodes/*.py
    db/                engines/pools, schema catalog (introspection), row-level security helpers
    safety/            sql_validator.py, mysql_row_filter.py
    rag/               embedding, Chroma access, retrieval
    semantic/          glossary.yaml + loader
    llm/               Ollama client, prompts
    observability/     audit log, metrics, logging
  scripts/
    setup_databases.py   download Synthea, create DBs, load, create read-only users, enable RLS (idempotent: --reset)
    fetch_drug_labels.py openFDA → chunks → ChromaDB
    run_eval.py
  eval/questions.yaml
  tests/
  .env.example
  requirements.txt
docs/
  how-it-works.md      plain-language explainer
  setup-windows.md     install PostgreSQL, MySQL, (optional) Ollama; get free Groq/Gemini API keys; run setup scripts
```

## 15. Milestones (each ends with tests passing and the explainer updated)

1. **Setup & data:** install guide; setup script loads both DBs, read-only users, Postgres RLS; `/health`.
2. **First answers:** LangGraph pipeline on `clinical_db` only — schema injection, SQL generation, validation, self-correction, synthesis with SQL + citations.
3. **Second database:** `billing_db`, routing, planning, cross-DB merge, MySQL row-filter rewrite, patient-mode refusals.
4. **Documents:** drug-label fetch + ChromaDB, RAG route, hybrid questions.
5. **Conversation:** follow-ups, clarification, out-of-scope, SSE streaming.
6. **Production habits:** caching, pagination, rate/concurrency limits, audit endpoint, metrics.
7. **Evaluation:** question set, harness, first report.

Later (separate request): Trino comparison mode; React frontend; login if wanted.

## 16. The explainer document (`docs/how-it-works.md`)

Audience: someone non-technical. Explains what the product does and what happens, step by step, when a question is asked,
using everyday analogies (the PDF's librarian / traffic-cop framing), with one real example question traced through every step,
plus a short glossary. Technical terms introduced only with a one-line plain meaning. Grows with each milestone.

## 17. Decisions made by Claude (owner may override)

- Lower-casing column names on load; table split as in §7.
- Two row-filtering techniques (Postgres RLS, MySQL rewrite) on purpose for learning.
- Patient mode refuses population/other-patient questions.
- Drug labels via openFDA API for in-use medications only (not the multi-GB bulk download).
- SQLite for app state; ChromaDB (not pgvector — avoids compiling extensions on Windows).
- Evaluation metrics as listed in §12.
- Patient mode hides population-statistic columns of payers/organizations/providers (§8).
- Hallucinated numbers are checked by code (verify_numbers); streamed answer text is held until checked (§9, §10).
- Eval is a measurement with informal targets, not a milestone gate; RAG/hybrid scored by expected facts (§12).
- Groq as the default free LLM provider (more generous free limits than Gemini, and it serves open-weight models);
  Gemini and local Ollama as switchable alternatives.

## 18. Left to the builder

Exact model names per provider (verify current free-tier models and limits at build time); local fallback model that fits 6 GB VRAM; prompt wording and few-shot examples; chunk sizes and top-k; cache TTL and limits;
eval question wording; Python version fallback (3.12 venv) if a dependency lacks 3.13 wheels.
