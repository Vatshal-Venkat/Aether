# Aether accuracy report — 2026-11-19 15:40

Model: `groq / openai/gpt-oss-120b` · questions: 48 (48 scored, 0 not run, 0 planned features)

## Overall: **47 / 48 correct (98%)**

| Measure | Result | Target (design §12) |
|---|---|---|
| Database questions answered correctly | 26 / 27 (96%) | ≥ 75% |
| Routed the right way | 39 / 39 (100%) | ≥ 90% |
| Privacy checks held | 12 / 12 | all |
| Typical answer time (median / slowest 5%) | 9.9 s / 32.0 s | under ~10 s |
| Questions that needed a SQL retry | 0 | — |
| Answers with unmatched numbers | 1 | — |

## By category

| Category | Correct | Ran | % |
|---|---|---|---|
| clinical | 12 | 12 | 100% |
| billing | 6 | 6 | 100% |
| cross_db | 4 | 5 | 80% |
| rag | 5 | 5 | 100% |
| hybrid | 3 | 3 | 100% |
| patient | 4 | 4 | 100% |
| privacy | 6 | 6 | 100% |
| safety | 3 | 3 | 100% |
| conversation | 4 | 4 | 100% |

## Time per step (median)

| Step | Median | Times run |
|---|---|---|
| generate_sql | 6.90 s | 33 |
| route | 2.72 s | 48 |
| synthesize | 1.61 s | 38 |
| retrieve | 0.92 s | 8 |
| execute | 0.01 s | 33 |
| validate | 0.00 s | 33 |
| inject_schema | 0.00 s | 33 |
| verify_numbers | 0.00 s | 38 |
| contextualize | 0.00 s | 48 |
| plan | 0.00 s | 33 |
| row_filter | 0.00 s | 33 |
| next_step | 0.00 s | 33 |
| merge | 0.00 s | 33 |
| refuse | 0.00 s | 8 |
| out_of_scope | 0.00 s | 1 |
| clarify | 0.00 s | 1 |

## Wrong answers

- **XD03** (cross_db) — Which insurance company paid for the most visits? Give its name.  
  Why: missing true value(s): Medicare  
  Answer: Medicaid Source: billing_db.payers
