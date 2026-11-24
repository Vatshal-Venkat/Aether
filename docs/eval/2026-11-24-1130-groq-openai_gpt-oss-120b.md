# Aether accuracy report — 2026-11-24 11:30

Model: `groq / openai/gpt-oss-120b` · questions: 53 (53 scored, 0 not run, 0 planned features)

## Overall: **46 / 53 correct (87%)**

| How | Questions |
|---|---|
| Right straight away | 43 / 53 (81%) |
| Right after one question back | 3 / 53 (6%) |
| Wrong | 7 / 53 (13%) |

When Aether asks back where an answer was expected, the test replies once like a person would (clicks "Yes, go ahead", or says what it meant) and scores the answer after that.

| Measure | Result | Target (design §12) |
|---|---|---|
| Database questions answered correctly | 24 / 30 (80%) | ≥ 75% |
| Routed the right way | 43 / 44 (98%) | ≥ 90% |
| Privacy checks held | 12 / 12 | all |
| Typical answer time (median / slowest 5%) | 10.8 s / 41.1 s | under ~10 s |
| Questions that needed a SQL retry | 2 | — |
| Answers with unmatched numbers | 0 | — |

## By category

| Category | Correct | Ran | % |
|---|---|---|---|
| clinical | 12 | 13 | 92% |
| billing | 4 | 6 | 67% |
| cross_db | 5 | 7 | 71% |
| rag | 6 | 6 | 100% |
| hybrid | 2 | 3 | 67% |
| patient | 3 | 4 | 75% |
| privacy | 6 | 6 | 100% |
| safety | 3 | 3 | 100% |
| conversation | 5 | 5 | 100% |

## Time per step (median)

| Step | Median | Times run |
|---|---|---|
| generate_sql | 9.48 s | 35 |
| route | 2.60 s | 53 |
| retrieve | 1.22 s | 8 |
| fail | 0.99 s | 1 |
| synthesize | 0.72 s | 41 |
| execute | 0.02 s | 35 |
| validate | 0.00 s | 35 |
| inject_schema | 0.00 s | 35 |
| verify_numbers | 0.00 s | 41 |
| contextualize | 0.00 s | 53 |
| plan | 0.00 s | 35 |
| row_filter | 0.00 s | 35 |
| next_step | 0.00 s | 35 |
| merge | 0.00 s | 35 |
| clarify | 0.00 s | 5 |
| refuse | 0.00 s | 7 |
| out_of_scope | 0.00 s | 2 |

## Asked back first

- **BI01** WRONG — Which insurance company has the most customers?  
  Aether asked: Do you want the insurance company with the most current customers or the one that has ever had the most customers?  
  Test replied: Yes, use the usual meaning in the data.
- **XD04** right — Which hospital or clinic had the most visits? Give its name.  
  Aether asked: To answer this I'd have to assume: hospital or clinic = organization of type hospital or clinic in billing DB. Is that what you mean?  
  Test replied: Which hospital or clinic had the most visits? Give its name. (hospital or clinic = organization of type hospital or clinic in billing DB)
- **XD05** right — What is the name of the doctor Angelyn934 Harris789 saw at her most recent visit?  
  Aether asked: I couldn't work out a query for that. Did you mean one of these?  
  Test replied: Yes, use the usual meaning in the data.
- **CV02** right — Insurers  
  Aether asked: Which entity's revenue are you asking about?  
  Test replied: The revenue figure recorded for each insurance company.

## Wrong answers

- **CL12** (clinical) — What is the most commonly prescribed medication?  
  Why: missing true value(s): lisinopril  
  Answer: The most commonly prescribed medication is **sodium fluoride 0.0272 MG/MG Oral Gel**, which was prescribed to **90 patients**. Source: clinical_db.medications.
- **BI01** (billing) — Which insurance company has the most customers?  
  Why: kind 'clarification', expected 'answer'; route 'clarify', expected 'sql'; missing true value(s): Medicaid  
  Answer: To answer this I'd have to assume: customers = patients whose current payer is the insurer (most recent payer_transition). Is that what you mean?
- **BI02** (billing) — How many hospitals or clinics are in Boston?  
  Why: missing true value(s): 14  
  Answer: There are **32** distinct hospitals or clinics that have encounters with patients residing in Boston. Source: clinical_db.encounters, clinical_db.patients
- **XD02** (cross_db) — What is the total outstanding patient balance on claims for patients with diabetes?  
  Why: missing true value(s): 211.38  
  Answer: The total outstanding patient balance on claims for patients with diabetes is **$779,415.28**. Source: clinical_db.conditions, clinical_db.patients, billing_db.claims_transactions
- **XD07** (cross_db) — Which patient owes us the most? Give the top 5.  
  Why: missing true value(s): Ignacio928, Hartmann983, Refugio197, Dare640; missing any of: 2313.07 / 2,313.07; missing any of: 211.38  
  Answer: **Top 5 patients by amount owed** | Rank | Patient | Amount Owed | |------|---------|------------| | 1 | Ms. Daniell603 Shantel839 Swift555 | 131,652.91 | | 2 | Mrs. Soon875 Koelpin146 | 108,338.47 | | 3 | Ms. Cleo27 Den
- **HY02** (hybrid) — Which of Angelyn934 Harris789's current medications have a boxed warning?  
  Why: missing any of: lisinopril; missing any of: metformin; missing any of: prasugrel; missing any of: carbamazepine  
  Answer: Naproxen 500 MG Oral Tablet has a boxed warning. **Source:** clinical_db.medications (current medication list) and openFDA label: Naproxen — Boxed warning.
- **PT02** (patient) — How much do I still owe on my claims?  
  Why: missing true value(s): 0.0  
