# Aether accuracy report — 2026-11-18 12:25

Model: `groq / openai/gpt-oss-120b` · questions: 46 (40 scored, 4 not run, 2 planned features)

## Overall: **38 / 40 correct (95%)**

| Measure | Result | Target (design §12) |
|---|---|---|
| Database questions answered correctly | 22 / 24 (92%) | ≥ 75% |
| Routed the right way | 37 / 37 (100%) | ≥ 90% |
| Privacy questions held | 6 / 6 | all |
| Typical answer time (median / slowest 5%) | 2.5 s / 26.6 s | under ~10 s |
| Questions that needed a SQL retry | 0 | — |
| Answers with unmatched numbers | 0 | — |

## By category

| Category | Correct | Ran | % |
|---|---|---|---|
| clinical | 11 | 12 | 92% |
| billing | 6 | 6 | 100% |
| cross_db | 4 | 5 | 80% |
| rag | 5 | 5 | 100% |
| hybrid | 2 | 2 | 100% |
| patient | 1 | 1 | 100% |
| privacy | 6 | 6 | 100% |
| safety | 3 | 3 | 100% |

## Time per step (median)

| Step | Median | Times run |
|---|---|---|
| retrieve | 1.66 s | 7 |
| generate_sql | 0.98 s | 26 |
| route | 0.74 s | 40 |
| synthesize | 0.62 s | 31 |
| execute | 0.01 s | 26 |
| validate | 0.00 s | 26 |
| inject_schema | 0.00 s | 26 |
| verify_numbers | 0.00 s | 31 |
| plan | 0.00 s | 26 |
| row_filter | 0.00 s | 26 |
| next_step | 0.00 s | 26 |
| merge | 0.00 s | 26 |
| refuse | 0.00 s | 8 |
| out_of_scope | 0.00 s | 1 |

## Wrong answers

- **CL10** (clinical) — Which diagnosis (disorder) affects the most patients?  
  Why: missing true value(s): Gingivitis  
  Answer: The diagnosis affecting the most patients is **Medication review due (situation)**, with **111** distinct patients. **Source:** clinical_db.conditions
- **XD04** (cross_db) — Which hospital or clinic had the most visits? Give its name.  
  Why: missing true value(s): ARBOUR-FULLER HOSPITAL  
  Answer: ARBOUR‑FULLER HOSPITAL had the most visits. Source: clinical_db.encounters, billing_db.organizations

## Not run (free AI tier rate-limited)

HY03, PT01, PT02, PT03

## Planned features (shown, not scored)

- **PL01** (Plan 4) — What's the revenue? → not yet
- **PL02** (Plan 4) — How many of them are female? → not yet
