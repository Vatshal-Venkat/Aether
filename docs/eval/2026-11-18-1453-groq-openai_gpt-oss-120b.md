# Aether accuracy report — 2026-11-18 14:53

Model: `groq / openai/gpt-oss-120b` · questions: 2 (2 scored, 0 not run, 0 planned features)

## Overall: **2 / 2 correct (100%)**

| Measure | Result | Target (design §12) |
|---|---|---|
| Database questions answered correctly | 1 / 1 (100%) | ≥ 75% |
| Routed the right way | 2 / 2 (100%) | ≥ 90% |
| Privacy questions held | 0 / 0 | all |
| Typical answer time (median / slowest 5%) | 27.6 s / 34.2 s | under ~10 s |
| Questions that needed a SQL retry | 0 | — |
| Answers with unmatched numbers | 0 | — |

## By category

| Category | Correct | Ran | % |
|---|---|---|---|
| hybrid | 1 | 1 | 100% |
| patient | 1 | 1 | 100% |

## Time per step (median)

| Step | Median | Times run |
|---|---|---|
| generate_sql | 10.69 s | 2 |
| route | 10.39 s | 2 |
| synthesize | 5.80 s | 2 |
| retrieve | 1.33 s | 1 |
| validate | 0.02 s | 2 |
| execute | 0.01 s | 2 |
| verify_numbers | 0.00 s | 2 |
| inject_schema | 0.00 s | 2 |
| merge | 0.00 s | 2 |
| plan | 0.00 s | 2 |
| next_step | 0.00 s | 2 |
| row_filter | 0.00 s | 2 |

## Wrong answers

None.
