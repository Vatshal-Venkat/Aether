# Plan 6 — Accuracy Report (Evaluation Harness) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** One command produces a dated, repeatable accuracy report for Aether: ~40 fixed questions across every capability, each scored by code against truth computed straight from the databases (no AI judge), with % correct per category, routing accuracy, refusal correctness, latency and retries.

**Architecture:** Questions live in `backend/app/eval/questions.yaml` (role, category, question, expected route/kind, and how to score: gold SQL run with the ADMIN connection, required facts, forbidden content). `app/eval/scoring.py` holds pure scoring functions. `scripts/run_eval.py` resolves patient names, computes gold answers, asks every question through the real pipeline (`run_chat`), scores, and writes `docs/eval/<date>-<model>.md` (+ `.json` raw). Free-tier aware: pacing between questions, waits and retries when rate-limited, and rate-limited questions are reported as "not run", never as wrong.

**Spec:** `docs/superpowers/specs/2026-11-17-healthcare-multidb-chatbot-design.md` §12 (eval harness, scoring by category, informal targets: routing ≥ 90%, SQL execution accuracy ≥ 75%, zero leaks).

## Global Constraints
- Deterministic scoring by code only (no LLM judge, saves quota, repeatable).
- Gold answers computed at run time with the admin connections (data can change; truth follows it).
- Questions about not-yet-built features (follow-ups, clarification: Plan 4) are included, marked `planned: "Plan 4"`, shown in the report but excluded from the overall score.
- No secrets or patient SSNs ever written to the report (privacy checks report pass/fail only).

## Review Focus
1. Number matching tolerates formatting (1,234.5 / 1234.50 / $1,234.50) but not wrong values. → `test_numbers_match_*`.
2. Synthea names match with or without digits ("Manuela585 Rendón540" / "Manuela Rendón"). → `test_name_match`.
3. A rate-limited run is "not run", not "wrong". → `test_rate_limited_case_is_not_run`.
4. Privacy cases fail if any other patient's name or an SSN-shaped value appears. → `test_privacy_scoring`.

### Task 1: Route kind in results + scoring library + question set
- `ChatResult.route: str | None` (the router's decision) — test in `tests/graph/test_build.py`.
- `app/eval/cases.py`: pydantic `EvalCase` (id, category, role, patient (name, optional), question, expect_kind, expect_route, gold {db, sql} optional, gold_check "all_values"|"any_value", must_contain [any-of groups], must_not_contain, source_prefix, privacy (bool), planned (optional)); `load_cases(path) -> list[EvalCase]` (ids unique).
- `app/eval/scoring.py`: `numbers_match(gold: float, answer: str) -> bool`, `name_in(name, answer) -> bool`, `values_in_answer(values, answer, mode) -> (ok, missing)`, `score_case(case, result, gold_rows, other_patient_names) -> CaseScore{id, category, correct, route_ok, kind_ok, reasons, seconds, retries, unverified, not_run}`.
- `app/eval/questions.yaml`: ~42 cases (clinical 12, billing 6, cross-DB 5, drug labels 5, hybrid 3, patient 4, privacy/safety 7, planned 2).
- Tests: `tests/eval/test_scoring.py`, `tests/eval/test_cases.py` (all YAML cases load; gold SQL parses; ids unique).

### Task 2: Runner + report
- `scripts/run_eval.py`: `--only ID,...`, `--category`, `--pause S` (default 3), `--out docs/eval`; resolves patients, computes gold, runs, retries rate-limited cases (wait 65 s, ≤ 2 retries), writes markdown + JSON. `render_report(scores, meta) -> str` pure (tested).
- Tests: `tests/eval/test_report.py` (`render_report` per-category table, overall excludes planned + not-run, privacy section never prints answer text), `test_rate_limited_case_is_not_run` (fake runner).

### Task 3: First real run + docs
- Run on the default model (as quota allows; partial runs are fine — the report says what ran). Fix real bugs found (test-first). Explain the report in `docs/how-it-works.md` (non-technical) and how to run it in `docs/setup-windows.md`.
