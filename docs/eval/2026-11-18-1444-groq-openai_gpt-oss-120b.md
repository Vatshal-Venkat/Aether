# Aether accuracy report — 2026-11-18 14:44

Model: `groq / openai/gpt-oss-120b` · questions: 6 (6 scored, 0 not run, 0 planned features)

## Overall: **4 / 6 correct (67%)**

| Measure | Result | Target (design §12) |
|---|---|---|
| Database questions answered correctly | 4 / 5 (80%) | ≥ 75% |
| Routed the right way | 6 / 6 (100%) | ≥ 90% |
| Privacy questions held | 0 / 0 | all |
| Typical answer time (median / slowest 5%) | 28.9 s / 53.8 s | under ~10 s |
| Questions that needed a SQL retry | 0 | — |
| Answers with unmatched numbers | 0 | — |

## By category

| Category | Correct | Ran | % |
|---|---|---|---|
| clinical | 1 | 1 | 100% |
| cross_db | 1 | 1 | 100% |
| hybrid | 0 | 1 | 0% |
| patient | 2 | 3 | 67% |

## Time per step (median)

| Step | Median | Times run |
|---|---|---|
| generate_sql | 11.43 s | 6 |
| route | 10.42 s | 6 |
| synthesize | 9.97 s | 6 |
| retrieve | 3.50 s | 1 |
| execute | 0.02 s | 6 |
| validate | 0.00 s | 6 |
| inject_schema | 0.00 s | 6 |
| verify_numbers | 0.00 s | 6 |
| plan | 0.00 s | 6 |
| row_filter | 0.00 s | 6 |
| next_step | 0.00 s | 6 |
| merge | 0.00 s | 6 |

## Wrong answers

- **HY03** (hybrid) — What is my metformin used for?  
  Why: missing any of: glycemic / blood sugar / glucose / diabetes  
  Answer: No records found for that question (searched clinical_db.supplies, openFDA label: Metformin Er 500 Mg — Uses).
- **PT01** (patient) — When was my last visit?  
  Why: missing true value(s): 2026-10-14  
  Answer: Your most recent visit was on **2026‑10‑14 at 08:09 UTC**. Source: clinical_db.encounters
