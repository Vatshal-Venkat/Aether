# Plan 5 — Production Habits: Cache, Paging, Limits, Audit, Metrics

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Aether behave like a service: repeat questions answer instantly from a cache, large tables arrive in pages, nobody can flood it, every request leaves an audit record, and live counters show how it is doing.

**Architecture:** A `ChatService` (backend/app/service.py) wraps the pipeline for both endpoints: rate limit → cache lookup → concurrency slot → run → store result pages → audit → metrics. The pipeline itself is unchanged. App state lives in SQLite under `backend/data/` (git-ignored).

**Spec:** `docs/superpowers/specs/2026-11-17-healthcare-multidb-chatbot-design.md` §10 (`/api/results/{id}?page`, `/api/audit`, `/metrics`), §11 (cache, semaphore, per-IP rate limit, 100 rows per page), §8 (audit record fields).

## Global Constraints
- Cache: in-memory LRU, 256 entries, TTL 10 min, key = (normalised question, role, patient_id, schema version). Only first questions of a conversation (no history) are cached — a follow-up depends on its conversation. Only `kind == "answer"` results are cached; never errors/refusals/clarifications. A cache hit still saves the conversation turn and is audited. `ChatResult.cached: bool`.
- Paging: API responses carry at most 100 table rows plus `result_id`; `GET /api/results/{id}?page=n&role=…&patient_id=…` returns 100-row pages; stored results expire after 30 min and are scoped to the asker (another role/patient gets 404).
- Limits: per-IP sliding window, 20 chat requests / 60 s (HTTP 429, `Retry-After`); at most 2 pipelines run at once (others wait; the free AI tier is the bottleneck).
- Audit (spec §8): timestamp, role, patient_id, question, standalone question, route, kind, each SQL with database + error, row count, cached, status, latency. SQLite `data/audit.sqlite`. `GET /api/audit?limit=` is **off unless `ENABLE_AUDIT_API=true`** — with no login, it would show every patient's questions to anyone.
- Metrics: Prometheus text at `GET /metrics` (prometheus-client): requests by kind, request latency histogram, per-step latency histogram, SQL errors, cache hits/misses, rate-limited count, in-flight pipelines.

## Review Focus
1. A cached answer must never be served to another role or patient. → `test_cache_scoped_to_role_and_patient`.
2. A follow-up (with history) is never served from cache. → `test_followups_bypass_cache`.
3. Result pages: another patient cannot page someone else's table. → `test_result_pages_scoped`.
4. The audit API is off by default. → `test_audit_api_disabled_by_default`.
5. Rate limit hits return a friendly 429, and the website shows it. → `test_rate_limit_429`, client mapping test.

### Task 1: Audit log + metrics
- `app/ops/audit.py`: `AuditLog(path)`: `record(entry: AuditEntry)`, `recent(limit) -> list[AuditEntry]`.
- `app/ops/metrics.py`: prometheus-client registry + helpers `observe_result(result, seconds, cached)`, `inc_rate_limited()`.
- `/metrics` route; `/api/audit` route behind `enable_audit_api`.
- Tests: audit roundtrip/ordering/limit; metrics text contains counters after an observed result; audit API 404 by default, 200 when enabled.

### Task 2: ChatService — cache + concurrency + audit/metrics wiring
- `app/service.py`: `ChatService(deps, settings)` with `answer(...) -> ChatResult` and `stream(...) -> Iterator[dict]`; LRU+TTL cache (`app/ops/cache.py`, injectable clock); `threading.BoundedSemaphore(max_concurrent_chats=2)`.
- Endpoints use the service. `ChatResult.cached`.
- Tests: hit returns same answer with `cached=True` and no AI call; scoping; follow-ups bypass; errors not cached; TTL expiry; turn saved + audited on hit; stream emits final for hits; semaphore caps concurrency.

### Task 3: Rate limit + result pages
- `app/ops/ratelimit.py`: sliding window per key; FastAPI dependency on chat endpoints → 429 with `Retry-After` and detail "Too many questions at once — please wait a moment."
- `app/ops/results.py`: TTL store of full result rows; service attaches `table.result_id`, trims rows to 100; `GET /api/results/{id}`.
- Tests: 429 after limit; window slides; pages content/bounds; scoping 404; expiry.

### Task 4: Website
- Client: 429 → "Too many questions at once — please wait a moment."; `getResultPage`.
- ResultTable: shows the first 100 rows; "Load more" fetches next pages until total; meta shows "from cache" for cached answers.
- Tests: client 429 mapping; load-more appends rows; cached badge.

### Task 5: Docs + live check
- Live: repeat question → instant cached answer; /metrics; audit records (with the API enabled locally); paging on "list all encounters". Update `docs/how-it-works.md`, `docs/setup-windows.md` (ENABLE_AUDIT_API, /metrics).
