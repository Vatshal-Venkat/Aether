# Aether accuracy report — 2026-11-19 15:58

Model: `groq / openai/gpt-oss-120b` · questions: 11 (11 scored, 0 not run, 0 planned features)

## Overall: **11 / 11 correct (100%)**

| Measure | Result | Target (design §12) |
|---|---|---|
| Database questions answered correctly | 11 / 11 (100%) | ≥ 75% |
| Routed the right way | 11 / 11 (100%) | ≥ 90% |
| Privacy checks held | 0 / 0 | all |
| Typical answer time (median / slowest 5%) | 8.2 s / 48.8 s | under ~10 s |
| Questions that needed a SQL retry | 0 | — |
| Answers with unmatched numbers | 0 | — |

## By category

| Category | Correct | Ran | % |
|---|---|---|---|
| billing | 6 | 6 | 100% |
| cross_db | 5 | 5 | 100% |

## Time per step (median)

| Step | Median | Times run |
|---|---|---|
| generate_sql | 2.88 s | 11 |
| route | 1.29 s | 11 |
| synthesize | 1.12 s | 11 |
| execute | 0.01 s | 11 |
| validate | 0.00 s | 11 |
| inject_schema | 0.00 s | 11 |
| verify_numbers | 0.00 s | 11 |
| contextualize | 0.00 s | 11 |
| plan | 0.00 s | 11 |
| row_filter | 0.00 s | 11 |
| next_step | 0.00 s | 11 |
| merge | 0.00 s | 11 |

## Wrong answers

None.
