# Aether accuracy report — 2026-11-23 17:57

Model: `groq / openai/gpt-oss-120b` · questions: 53 (53 scored, 0 not run, 0 planned features)

## Overall: **44 / 53 correct (83%)**

| Measure | Result | Target (design §12) |
|---|---|---|
| Database questions answered correctly | 24 / 30 (80%) | ≥ 75% |
| Routed the right way | 36 / 44 (82%) | ≥ 90% |
| Privacy checks held | 12 / 12 | all |
| Typical answer time (median / slowest 5%) | 10.7 s / 29.8 s | under ~10 s |
| Questions that needed a SQL retry | 1 | — |
| Answers with unmatched numbers | 0 | — |

## By category

| Category | Correct | Ran | % |
|---|---|---|---|
| clinical | 12 | 13 | 92% |
| billing | 5 | 6 | 83% |
| cross_db | 4 | 7 | 57% |
| rag | 6 | 6 | 100% |
| hybrid | 2 | 3 | 67% |
| patient | 3 | 4 | 75% |
| privacy | 6 | 6 | 100% |
| safety | 3 | 3 | 100% |
| conversation | 3 | 5 | 60% |

## Time per step (median)

| Step | Median | Times run |
|---|---|---|
| generate_sql | 6.16 s | 29 |
| fail | 5.09 s | 1 |
| route | 4.31 s | 53 |
| synthesize | 1.38 s | 33 |
| retrieve | 0.55 s | 7 |
| execute | 0.01 s | 28 |
| validate | 0.00 s | 29 |
| inject_schema | 0.00 s | 29 |
| verify_numbers | 0.00 s | 33 |
| contextualize | 0.00 s | 53 |
| plan | 0.00 s | 29 |
| row_filter | 0.00 s | 28 |
| next_step | 0.00 s | 28 |
| merge | 0.00 s | 28 |
| clarify | 0.00 s | 10 |
| refuse | 0.00 s | 7 |
| out_of_scope | 0.00 s | 2 |

## Wrong answers

- **CL04** (clinical) — How many emergency visits were there?  
  Why: kind 'clarification', expected 'answer'; route 'clarify', expected 'sql'; missing true value(s): 195  
  Answer: To answer this I'd have to assume: emergency = visits where the encounter type is marked as 'Emergency'. Is that what you mean?
- **BI05** (billing) — Which insurance company has the highest revenue?  
  Why: kind 'clarification', expected 'answer'; route 'clarify', expected 'sql'; missing true value(s): UnitedHealthcare  
  Answer: What do you mean by 'revenue' for the insurance company?
- **XD02** (cross_db) — What is the total outstanding patient balance on claims for patients with diabetes?  
  Why: kind 'clarification', expected 'answer'; route 'clarify', expected 'sql'; missing true value(s): 211.38  
  Answer: To answer this I'd have to assume: diabetes = a diagnosis record indicating diabetes in the clinical diagnoses table; outstanding patient balance = the current balance field on claims representing patient responsibility.
- **XD03** (cross_db) — Which insurance company paid for the most visits? Give its name.  
  Why: kind 'clarification', expected 'answer'; route 'clarify', expected 'sql'; missing true value(s): Medicare  
  Answer: To answer this I'd have to assume: paid = a claim associated with the visit that has a payment amount > 0; each visit is linked to a claim via encounter_id or similar identifier. Is that what you mean?
- **XD06** (cross_db) — Which patient owes us the most money? Give the name and the amount.  
  Why: kind 'clarification', expected 'answer'; route 'clarify', expected 'sql'; missing true value(s): Refugio197, Dare640; missing any of: 2313.07 / 2,313.07  
  Answer: To answer this I'd have to assume: most money = highest total outstanding balance across all claims for the patient. Is that what you mean?
- **HY02** (hybrid) — Which of Angelyn934 Harris789's current medications have a boxed warning?  
  Why: kind 'clarification', expected 'answer'; route 'clarify', expected 'hybrid'; missing any of: lisinopril; missing any of: metformin; missing any of: naproxen; missing any of: prasugrel; missing any of: carbamazepine  
  Answer: To answer this I'd have to assume: current medications = prescriptions with a start date before today and no stop date or a stop date in the future. Is that what you mean?
- **PT04** (patient) — How many different medications am I currently taking?  
  Why: kind 'clarification', expected 'answer'; route 'clarify', expected 'sql'; missing true value(s): 13  
- **CV02** (conversation) — Insurers  
  Why: kind 'clarification', expected 'answer'; route 'clarify', expected 'sql'; missing true value(s): 8447792.84, UnitedHealthcare  
  Answer: Which revenue metric are you interested in?
- **CV05** (conversation) — Show their names  
  Why: kind 'clarification', expected 'answer'; missing true value(s): Angelyn934, Harris789, Denisha680, Kuphal363, Ignacio928  
  Answer: I couldn't work out a query for that. Did you mean one of these?
