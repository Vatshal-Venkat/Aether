# Aether accuracy report — 2026-11-24 14:41

Model: `groq / openai/gpt-oss-120b` · questions: 5 (5 scored, 0 not run, 0 planned features)

## Overall: **4 / 5 correct (80%)**

| How | Questions |
|---|---|
| Right straight away | 4 / 5 (80%) |
| Right after one question back | 0 / 5 (0%) |
| Wrong | 1 / 5 (20%) |

When Aether asks back where an answer was expected, the test replies once like a person would (clicks "Yes, go ahead", or says what it meant) and scores the answer after that.

| Measure | Result | Target (design §12) |
|---|---|---|
| Database questions answered correctly | 4 / 5 (80%) | ≥ 75% |
| Routed the right way | 5 / 5 (100%) | ≥ 90% |
| Privacy checks held | 0 / 0 | all |
| Typical answer time (median / slowest 5%) | 2.5 s / 33.0 s | under ~10 s |
| Questions that needed a SQL retry | 1 | — |
| Answers with unmatched numbers | 0 | — |

## By category

| Category | Correct | Ran | % |
|---|---|---|---|
| clinical | 1 | 1 | 100% |
| billing | 2 | 2 | 100% |
| cross_db | 1 | 2 | 50% |

## Time per step (median)

| Step | Median | Times run |
|---|---|---|
| generate_sql | 1.17 s | 5 |
| synthesize | 0.72 s | 5 |
| route | 0.66 s | 5 |
| execute | 0.03 s | 5 |
| validate | 0.01 s | 5 |
| inject_schema | 0.00 s | 5 |
| verify_numbers | 0.00 s | 5 |
| contextualize | 0.00 s | 5 |
| plan | 0.00 s | 5 |
| row_filter | 0.00 s | 5 |
| next_step | 0.00 s | 5 |
| merge | 0.00 s | 5 |

## Answered with help from a backup model

5 answers were written (partly) by a backup model after short rate limits on `openai/gpt-oss-120b`; 4 of them right.

- **CL12** right — openai/gpt-oss-20b, openai/gpt-oss-120b
- **BI01** right — openai/gpt-oss-20b, openai/gpt-oss-120b
- **BI02** right — openai/gpt-oss-20b, openai/gpt-oss-120b
- **XD02** WRONG — openai/gpt-oss-20b, openai/gpt-oss-120b
- **XD07** right — openai/gpt-oss-20b, openai/gpt-oss-120b

## Wrong answers

- **XD02** (cross_db) — What is the total outstanding patient balance on claims for patients with diabetes?  
  Why: missing true value(s): 211.38  
  Answer: The total outstanding patient balance on claims for patients with diabetes is **$845.52**. Source: clinical_db.conditions, clinical_db.patients, billing_db.claims, billing_db.claims_transactions
