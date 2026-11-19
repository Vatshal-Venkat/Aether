# Aether accuracy report — 2026-11-19 17:06

Model: `groq / openai/gpt-oss-20b` · questions: 50 (50 scored, 0 not run, 0 planned features)

## Overall: **45 / 50 correct (90%)**

| Measure | Result | Target (design §12) |
|---|---|---|
| Database questions answered correctly | 26 / 29 (90%) | ≥ 75% |
| Routed the right way | 40 / 41 (98%) | ≥ 90% |
| Privacy checks held | 12 / 12 | all |
| Typical answer time (median / slowest 5%) | 2.4 s / 13.7 s | under ~10 s |
| Questions that needed a SQL retry | 1 | — |
| Answers with unmatched numbers | 1 | — |

## By category

| Category | Correct | Ran | % |
|---|---|---|---|
| clinical | 11 | 12 | 92% |
| billing | 6 | 6 | 100% |
| cross_db | 5 | 7 | 71% |
| rag | 4 | 5 | 80% |
| hybrid | 3 | 3 | 100% |
| patient | 4 | 4 | 100% |
| privacy | 6 | 6 | 100% |
| safety | 3 | 3 | 100% |
| conversation | 3 | 4 | 75% |

## Time per step (median)

| Step | Median | Times run |
|---|---|---|
| generate_sql | 0.93 s | 33 |
| route | 0.65 s | 50 |
| synthesize | 0.55 s | 38 |
| retrieve | 0.45 s | 8 |
| execute | 0.01 s | 33 |
| validate | 0.00 s | 33 |
| inject_schema | 0.00 s | 33 |
| verify_numbers | 0.00 s | 38 |
| contextualize | 0.00 s | 50 |
| plan | 0.00 s | 33 |
| row_filter | 0.00 s | 33 |
| next_step | 0.00 s | 33 |
| merge | 0.00 s | 32 |
| fail | 0.00 s | 1 |
| refuse | 0.00 s | 8 |
| out_of_scope | 0.00 s | 1 |
| clarify | 0.00 s | 2 |

## Wrong answers

- **CL08** (clinical) — What is Angelyn934 Harris789's most recent HbA1c value?  
  Why: missing true value(s): 3.1  
  Answer: No records found for that question (searched clinical_db.observations).
- **XD06** (cross_db) — Which patient owes us the most money? Give the name and the amount.  
  Why: kind 'error', expected 'answer'; missing true value(s): Refugio197, Dare640; missing any of: 2313.07 / 2,313.07  
  Answer: I couldn't build a working query for that after 3 tries. Try rephrasing, or ask something more specific.
- **XD07** (cross_db) — Which patient owes us the most? Give the top 5.  
  Why: missing true value(s): Ignacio928, Hartmann983, Refugio197, Dare640  
  Answer: **Patients owed (top 5, with all tied rows shown)** | Rank | Patient ID | Total owed | |------|------------|------------| | 1 | 2571ad10‑0831‑bf71‑4731‑6f7c298b20c7 | 2313.07 | | 2 | 10bb8914‑0338‑90ea‑87ff‑9231ff231563 
- **RG04** (rag) — Can naproxen be taken together with lisinopril?  
  Why: missing any of: kidney / renal / blood pressure / antihypertensive  
  Answer: Naproxen can be taken while a patient is on lisinopril, but the label warns that NSAIDs—including naproxen—can blunt the blood‑pressure‑lowering effect of ACE inhibitors and may worsen hypertension. Careful blood‑pressur
- **CV02** (conversation) — Insurers  
  Why: kind 'clarification', expected 'answer'; route 'clarify', expected 'sql'; missing true value(s): 8447792.84, UnitedHealthcare  
  Answer: Do you want the revenue the hospital/clinic receives from insurers, or the revenue insurers generate from their operations?
