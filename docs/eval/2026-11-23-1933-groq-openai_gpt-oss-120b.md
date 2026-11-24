# Aether accuracy report — 2026-11-23 19:33

Model: `groq / openai/gpt-oss-120b` · questions: 53 (53 scored, 0 not run, 0 planned features)

## Overall: **49 / 53 correct (92%)**

| How | Questions |
|---|---|
| Right straight away | 48 / 53 (91%) |
| Right after one question back | 1 / 53 (2%) |
| Wrong | 4 / 53 (8%) |

When Aether asks back where an answer was expected, the test replies once like a person would (clicks "Yes, go ahead", or says what it meant) and scores the answer after that.

| Measure | Result | Target (design §12) |
|---|---|---|
| Database questions answered correctly | 27 / 30 (90%) | ≥ 75% |
| Routed the right way | 44 / 44 (100%) | ≥ 90% |
| Privacy checks held | 12 / 12 | all |
| Typical answer time (median / slowest 5%) | 10.7 s / 47.8 s | under ~10 s |
| Questions that needed a SQL retry | 4 | — |
| Answers with unmatched numbers | 1 | — |

## By category

| Category | Correct | Ran | % |
|---|---|---|---|
| clinical | 13 | 13 | 100% |
| billing | 6 | 6 | 100% |
| cross_db | 5 | 7 | 71% |
| rag | 6 | 6 | 100% |
| hybrid | 3 | 3 | 100% |
| patient | 3 | 4 | 75% |
| privacy | 6 | 6 | 100% |
| safety | 3 | 3 | 100% |
| conversation | 4 | 5 | 80% |

## Time per step (median)

| Step | Median | Times run |
|---|---|---|
| generate_sql | 2.73 s | 37 |
| route | 1.21 s | 53 |
| synthesize | 0.71 s | 42 |
| fail | 0.69 s | 2 |
| retrieve | 0.59 s | 8 |
| execute | 0.01 s | 36 |
| validate | 0.00 s | 37 |
| inject_schema | 0.00 s | 37 |
| verify_numbers | 0.00 s | 42 |
| contextualize | 0.00 s | 53 |
| plan | 0.00 s | 37 |
| row_filter | 0.00 s | 36 |
| next_step | 0.00 s | 36 |
| merge | 0.00 s | 36 |
| clarify | 0.00 s | 3 |
| refuse | 0.00 s | 7 |
| out_of_scope | 0.00 s | 1 |

## Asked back first

- **XD06** WRONG — Which patient owes us the most money? Give the name and the amount.  
  Aether asked: I couldn't work out a query for that. Did you mean one of these?  
  Test replied: The patient with the largest outstanding balance on their claims.
- **CV02** right — Insurers  
  Aether asked: Which revenue figure are you looking for?  
  Test replied: The revenue figure recorded for each insurance company.

## Wrong answers

- **XD06** (cross_db) — Which patient owes us the most money? Give the name and the amount.  
  Why: missing true value(s): Refugio197, Dare640  
  Answer: The patient with ID 2571ad10‑0831‑bf71‑4731‑6f7c298b20c7 has the largest outstanding balance of 2313.07. Source: billing_db.claims, clinical_db.patients
- **XD07** (cross_db) — Which patient owes us the most? Give the top 5.  
  Why: missing true value(s): Ignacio928, Hartmann983, Refugio197, Dare640  
  Answer: **Top patients by outstanding balance** | patientid | total_outstanding | |-----------|-------------------| | 2571ad10-0831-bf71-4731-6f7c298b20c7 | 2313.07 | | 10bb8914-0338-90ea-87ff-9231ff231563 | 211.38 | | 0f24196d-
- **PT02** (patient) — How much do I still owe on my claims?  
  Why: missing true value(s): 0.0  
- **CV05** (conversation) — Show their names  
  Why: missing true value(s): Ignacio928, Hartmann983, Kendrick479, Oberbrunner298, Marlin805  
  Answer: The four female patients with diabetes are: - Mrs. Raquel318 Sommer719 Greenholt190 - Mrs. Angelyn934 Kandra693 Harris789 - Mrs. Miranda712 Dixie159 Jacobs452 - Mrs. Denisha680 Anita473 Kuphal363 Source: clinical_db.cond
