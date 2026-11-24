# Aether accuracy report — 2026-11-23 20:42

Model: `groq / openai/gpt-oss-120b` · questions: 5 (1 scored, 4 not run, 0 planned features)

## Overall: **1 / 1 correct (100%)**

| How | Questions |
|---|---|
| Right straight away | 1 / 1 (100%) |
| Right after one question back | 0 / 1 (0%) |
| Wrong | 0 / 1 (0%) |

When Aether asks back where an answer was expected, the test replies once like a person would (clicks "Yes, go ahead", or says what it meant) and scores the answer after that.

| Measure | Result | Target (design §12) |
|---|---|---|
| Database questions answered correctly | 1 / 1 (100%) | ≥ 75% |
| Routed the right way | 1 / 1 (100%) | ≥ 90% |
| Privacy checks held | 0 / 0 | all |
| Typical answer time (median / slowest 5%) | 2.4 s / 2.4 s | under ~10 s |
| Questions that needed a SQL retry | 0 | — |
| Answers with unmatched numbers | 0 | — |

## By category

| Category | Correct | Ran | % |
|---|---|---|---|
| clinical | 1 | 1 | 100% |

## Time per step (median)

| Step | Median | Times run |
|---|---|---|
| route | 0.94 s | 1 |
| generate_sql | 0.91 s | 1 |
| synthesize | 0.48 s | 1 |
| execute | 0.04 s | 1 |
| validate | 0.02 s | 1 |
| inject_schema | 0.00 s | 1 |
| verify_numbers | 0.00 s | 1 |
| contextualize | 0.00 s | 1 |
| plan | 0.00 s | 1 |
| row_filter | 0.00 s | 1 |
| next_step | 0.00 s | 1 |
| merge | 0.00 s | 1 |

## Wrong answers

None.

## Not run (free AI tier rate-limited)

XD06, XD07, PT02, CV05
