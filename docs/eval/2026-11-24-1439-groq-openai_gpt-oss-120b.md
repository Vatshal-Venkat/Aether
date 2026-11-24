# Aether accuracy report — 2026-11-24 14:39

Model: `groq / openai/gpt-oss-120b` · questions: 5 (5 scored, 0 not run, 0 planned features)

## Overall: **0 / 5 correct (0%)**

| How | Questions |
|---|---|
| Right straight away | 0 / 5 (0%) |
| Right after one question back | 0 / 5 (0%) |
| Wrong | 5 / 5 (100%) |

When Aether asks back where an answer was expected, the test replies once like a person would (clicks "Yes, go ahead", or says what it meant) and scores the answer after that.

| Measure | Result | Target (design §12) |
|---|---|---|
| Database questions answered correctly | 0 / 5 (0%) | ≥ 75% |
| Routed the right way | 0 / 5 (0%) | ≥ 90% |
| Privacy checks held | 0 / 0 | all |
| Typical answer time (median / slowest 5%) | 0.0 s / 0.0 s | under ~10 s |
| Questions that needed a SQL retry | 0 | — |
| Answers with unmatched numbers | 0 | — |

## By category

| Category | Correct | Ran | % |
|---|---|---|---|
| clinical | 0 | 1 | 0% |
| billing | 0 | 2 | 0% |
| cross_db | 0 | 2 | 0% |

## Wrong answers

- **CL12** (clinical) — Which medication has been prescribed the most times?  
  Why: kind 'error', expected 'answer'; route None, expected 'sql'; missing true value(s): lisinopril  
  Answer: Something went wrong while answering. The details are in the server log.
- **BI01** (billing) — Which insurance company has the most customers?  
  Why: kind 'error', expected 'answer'; route None, expected 'sql'; missing true value(s): Medicaid  
  Answer: Something went wrong while answering. The details are in the server log.
- **BI02** (billing) — How many hospitals or clinics are in Boston?  
  Why: kind 'error', expected 'answer'; route None, expected 'sql'; missing true value(s): 14  
  Answer: Something went wrong while answering. The details are in the server log.
- **XD02** (cross_db) — What is the total outstanding patient balance on claims for patients with diabetes?  
  Why: kind 'error', expected 'answer'; route None, expected 'sql'; missing true value(s): 211.38  
  Answer: Something went wrong while answering. The details are in the server log.
- **XD07** (cross_db) — Which patient owes us the most? Give the top 5.  
  Why: kind 'error', expected 'answer'; route None, expected 'sql'; missing true value(s): Ignacio928, Hartmann983, Refugio197, Dare640; missing any of: 2313.07 / 2,313.07; missing any of: 211.38; missing any of: tie / tied / same amount / equal  
  Answer: Something went wrong while answering. The details are in the server log.
