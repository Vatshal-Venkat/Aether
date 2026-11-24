# Aether accuracy report — 2026-11-24 14:44

Model: `groq / openai/gpt-oss-120b` · questions: 1 (1 scored, 0 not run, 0 planned features)

## Overall: **1 / 1 correct (100%)**

| How | Questions |
|---|---|
| Right straight away | 0 / 1 (0%) |
| Right after one question back | 1 / 1 (100%) |
| Wrong | 0 / 1 (0%) |

When Aether asks back where an answer was expected, the test replies once like a person would (clicks "Yes, go ahead", or says what it meant) and scores the answer after that.

| Measure | Result | Target (design §12) |
|---|---|---|
| Database questions answered correctly | 1 / 1 (100%) | ≥ 75% |
| Routed the right way | 1 / 1 (100%) | ≥ 90% |
| Privacy checks held | 0 / 0 | all |
| Typical answer time (median / slowest 5%) | 121.4 s / 121.4 s | under ~10 s |
| Questions that needed a SQL retry | 0 | — |
| Answers with unmatched numbers | 0 | — |

## By category

| Category | Correct | Ran | % |
|---|---|---|---|
| cross_db | 1 | 1 | 100% |

## Time per step (median)

| Step | Median | Times run |
|---|---|---|
| fail | 94.32 s | 1 |
| generate_sql | 13.18 s | 1 |
| synthesize | 9.61 s | 1 |
| plan | 1.97 s | 1 |
| route | 1.46 s | 1 |
| contextualize | 0.69 s | 1 |
| execute | 0.14 s | 1 |
| validate | 0.04 s | 1 |
| inject_schema | 0.00 s | 1 |
| row_filter | 0.00 s | 1 |
| verify_numbers | 0.00 s | 1 |
| next_step | 0.00 s | 1 |
| merge | 0.00 s | 1 |

## Asked back first

- **XD02** right — What is the total outstanding patient balance on claims for patients with diabetes?  
  Aether asked: I couldn't work out a query for that. Did you mean one of these?  
  Test replied: Yes, use the usual meaning in the data.

## Answered with help from a backup model

1 answers were written (partly) by a backup model after short rate limits on `openai/gpt-oss-120b`; 1 of them right.

- **XD02** right — openai/gpt-oss-20b, openai/gpt-oss-120b, gemini-2.5-flash

## Wrong answers

None.
