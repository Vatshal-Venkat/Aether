"""Answer writing (synthesize) and the number check that follows it (verify_numbers)."""

from app.graph.nodes.synthesize import synthesize
from app.graph.nodes.verify_numbers import verify_numbers
from app.graph.state import QueryResult
from tests.fakes import ScriptedLLM, make_deps


def test_answer_rules_cover_credits_and_ties():
    # Live (2026-11-19): a "top 5 who owe us" table listed a negative balance as owing, and hid a 5-way tie.
    from app.graph.nodes.synthesize import SYSTEM
    assert "negative balance" in SYSTEM and "credit" in SYSTEM
    assert "tied" in SYSTEM


def test_tie_note_spells_out_a_tie_at_the_cut_off():
    # Live (20b, 2026-11-19): 9 rows came back for "top 5" (7 tied at 42.28) but the answer listed 5, no tie.
    from app.graph.nodes.synthesize import tie_note
    rows = [["a", 2313.07], ["b", 211.38]] + [[c, 42.28] for c in "cdefghi"]
    result = QueryResult(columns=["patientid", "total_owed"], rows=rows, total_rows=9, truncated=False)
    note = tie_note("Which patient owes us the most? give top 5", result)
    assert note and "top 5" in note and "9 rows" in note and "rows 3-9" in note and "42.28" in note
    assert tie_note("Which patient owes us the most? give top 9", result) is None   # nothing was added
    assert tie_note("Which patients owe us money?", result) is None                 # no "top N" asked
    no_tie = QueryResult(columns=["p", "n"], rows=[["a", 3], ["b", 2], ["c", 1]], total_rows=3, truncated=False)
    assert tie_note("top 2 please", no_tie) is None                                 # extra rows, but no tie


def test_tie_note_reaches_the_prompt():
    rows = [["a", 5], ["b", 4], ["c", 4], ["d", 4]]
    state = {**_state(rows, columns=("name", "n")), "question": "Top 2 doctors by visits?"}
    llm = ScriptedLLM("a has 5; b, c and d are tied with 4.\nSource: clinical_db.patients")
    synthesize(state, make_deps(llm))
    assert "rows 2-4" in llm.prompt_text() and "tied" in llm.prompt_text()


def test_sql_rules_keep_ties_in_top_n():
    from app.llm.prompts import sql_system
    assert "RANK()" in sql_system("PostgreSQL", "clinician")


def _state(rows, columns=("n",)):
    return {
        "question": "How many patients are there?",
        "role": "clinician",
        "final_sql": "SELECT count(*) AS n FROM patients LIMIT 1000",
        "sources": ["clinical_db.patients"],
        "result": QueryResult(columns=list(columns), rows=rows, total_rows=len(rows), truncated=False),
    }


def test_empty_result_no_llm_call():
    out = synthesize(_state([]), make_deps(ScriptedLLM()))  # ScriptedLLM with no replies raises if called
    assert out["kind"] == "answer"
    assert out["answer"].startswith("No records found")


def test_all_null_result_counts_as_no_records():
    # Review I2: "SELECT max(date) FROM allergies" for someone with no allergies returns [[None]].
    out = synthesize(_state([[None]], columns=("last_allergy",)), make_deps(ScriptedLLM()))
    assert out["answer"].startswith("No records found")


def test_synthesize_uses_rows_and_sources_in_prompt():
    llm = ScriptedLLM("There are 111 patients (source: clinical_db.patients).")
    out = synthesize(_state([[111]]), make_deps(llm))
    assert out["answer"].startswith("There are 111 patients")
    prompt = llm.prompt_text()
    assert "111" in prompt and "clinical_db.patients" in prompt
    assert "internal id" in prompt.lower()  # tells the AI not to show UUIDs unless asked


def test_many_rows_asks_for_summary_not_full_list():
    # Live test: "List all encounters" took 63 s because the AI wrote out 50 rows.
    rows = [[f"row{i}"] for i in range(40)]
    llm = ScriptedLLM("There are 40 rows; the full table is attached.")
    synthesize(_state(rows, columns=("x",)), make_deps(llm))
    prompt = llm.prompt_text().lower()
    assert "do not list them all" in prompt
    assert prompt.count("row") < 30  # only a sample of rows is sent, not all 40


def test_prompt_asks_for_digits():
    llm = ScriptedLLM("There are 111 patients.")
    synthesize(_state([[111]]), make_deps(llm))
    assert "digits" in llm.prompt_text().lower()


def test_verify_passes_clean_answer_without_llm():
    state = {**_state([[111]]), "answer": "There are 111 patients."}
    out = verify_numbers(state, make_deps(ScriptedLLM()))
    assert out["unverified_numbers"] == []
    assert "answer" not in out or out["answer"] == "There are 111 patients."


def test_verify_resynthesizes_once():
    llm = ScriptedLLM("There are 111 patients.")
    state = {**_state([[111]]), "answer": "There are 112 patients."}
    out = verify_numbers(state, make_deps(llm))
    assert out["answer"] == "There are 111 patients."
    assert out["unverified_numbers"] == []
    assert "112" in llm.prompt_text()  # the correction prompt names the bad number


def test_verify_flags_after_second_failure():
    llm = ScriptedLLM("There are 113 patients.")
    state = {**_state([[111]]), "answer": "There are 112 patients."}
    out = verify_numbers(state, make_deps(llm))
    assert out["unverified_numbers"] == ["113"]
    assert "could not be matched" in out["answer"]


def test_patient_mode_answer_knows_rows_are_the_patients_own():
    # Live test P3 (smaller model): a patient asked for ANOTHER patient's medications, the router let it
    # through, and the database correctly returned only her own rows — but the answer presented them as
    # if they answered the question. The answer-writer must know the rows are always the asker's own.
    llm = ScriptedLLM("I can only show your own records.")
    synthesize({**_state([[3]]), "role": "patient", "patient_id": "p1"}, make_deps(llm))
    system = str(llm.calls[0][0].content)
    assert "only the current patient's own records" in system
    assert "about someone else" in system
    llm2 = ScriptedLLM("There are 3.")
    synthesize(_state([[3]]), make_deps(llm2))
    assert "only the current patient's own records" not in str(llm2.calls[0][0].content)


# --- highest / lowest over ALL rows (live 2026-11-20: "a peak of 382 in 2018" — the AI saw 10 of 17 rows) -------
VISIT_ROWS = [[2010 + i, v] for i, v in enumerate([31, 47, 49, 82, 67, 50, 135, 330, 382, 330, 357, 502, 412, 367,
                                                   410, 344, 366])]


def test_a_sampled_table_comes_with_code_computed_extremes():
    llm = ScriptedLLM("Visits peaked at 502 in 2021.\nSource: clinical_db.encounters")
    synthesize({**_state(VISIT_ROWS, columns=("year", "visits")), "question": "Visits each year since 2010?"},
               make_deps(llm))
    prompt = llm.prompt_text()
    assert "showing 10" in prompt and "2021 | 502" not in prompt  # the AI sees only a sample...
    assert "highest 502 (year 2021)" in prompt                    # ...plus the extremes over all 17 rows
    assert "only from these" in prompt.lower()


def test_a_small_table_needs_no_extremes_note():
    llm = ScriptedLLM("Ann has 5.\nSource: clinical_db.patients")
    synthesize(_state([["Ann", 5], ["Bob", 3]], columns=("name", "n")), make_deps(llm))
    assert "highest" not in llm.prompt_text().lower().split("question:")[1]


def test_verify_rewrites_a_wrong_peak_once():
    llm = ScriptedLLM("Visits peaked at 502 in 2021.")
    state = {**_state(VISIT_ROWS, columns=("year", "visits")), "answer": "Visits peaked at 382 in 2018."}
    out = verify_numbers(state, make_deps(llm))
    assert out["answer"] == "Visits peaked at 502 in 2021." and out["unverified_numbers"] == []
    assert "the highest visits is 502" in llm.prompt_text()  # the correction says what's wrong


def test_verify_flags_a_wrong_peak_that_survives_the_rewrite():
    llm = ScriptedLLM("Visits peaked at 382 in 2018.")
    state = {**_state(VISIT_ROWS, columns=("year", "visits")), "answer": "Visits peaked at 382 in 2018."}
    out = verify_numbers(state, make_deps(llm))
    assert out["unverified_numbers"] == ["382 (called the highest; the highest visits is 502)"]


# --- rows are not patients (live 2026-11-20: 19 diagnosis rows of 8 people were called "19 patients") ------------
def test_sql_rules_ask_for_one_row_per_patient():
    from app.llm.prompts import sql_system
    assert "ONE row per patient" in sql_system("PostgreSQL", "clinician")


def test_the_answer_writer_is_told_rows_are_not_patients():
    rows = [["p1", "Ann", "Diabetes"], ["p1", "Ann", "Neuropathy"], ["p2", "Bob", "Diabetes"]]
    llm = ScriptedLLM("2 patients: Ann and Bob.\nSource: clinical_db.conditions")
    synthesize(_state(rows, columns=("patient_id", "first", "condition")), make_deps(llm))
    assert "3 rows cover only 2 different patients" in llm.prompt_text()


def test_verify_rewrites_rows_called_patients():
    rows = [["p1", "Ann", "Diabetes"], ["p1", "Ann", "Neuropathy"], ["p2", "Bob", "Diabetes"]]
    llm = ScriptedLLM("2 patients have diabetes: Ann and Bob.")
    state = {**_state(rows, columns=("patient_id", "first", "condition")), "answer": "3 patients have diabetes."}
    out = verify_numbers(state, make_deps(llm))
    assert out["answer"] == "2 patients have diabetes: Ann and Bob." and out["unverified_numbers"] == []
    assert "cover 2 different patients" in llm.prompt_text()


def test_an_empty_ai_reply_is_retried_once():
    # Live (2026-11-20): the answer came back empty.
    llm = ScriptedLLM("", "There are 3.\nSource: clinical_db.patients")
    out = synthesize(_state([[3]]), make_deps(llm))
    assert out["answer"].startswith("There are 3.")


def test_two_empty_replies_give_a_plain_message_not_nothing():
    out = synthesize(_state([[3]]), make_deps(ScriptedLLM("", "  ")))
    assert "table" in out["answer"].lower() and out["answer"].strip()


# Accuracy report 2026-11-24 (PT02): "How much do I still owe?" for a patient who owes nothing ran
# SUM(outstandingp) ... WHERE outstandingp > 0 -> [[None]] -> "No records found". A total over nothing is 0.
def test_a_total_over_nothing_is_zero_not_no_records():
    state = {**_state([[None]], columns=("total_outstanding",)), "question": "How much do I still owe?",
             "final_sql": "SELECT SUM(outstandingp) AS total_outstanding FROM claims WHERE outstandingp > 0 LIMIT 1001"}
    llm = ScriptedLLM("You owe $0.00 on your claims.\nSource: billing_db.claims")
    out = synthesize(state, make_deps(llm))
    assert out["answer"].startswith("You owe $0.00")
    assert "| 0 |" in llm.prompt_text() or "0" in llm.prompt_text().split("Query results")[-1]


def test_max_over_nothing_is_still_no_records():
    state = {**_state([[None]], columns=("last_visit",)), "final_sql": "SELECT MAX(start) AS last_visit FROM encounters"}
    assert synthesize(state, make_deps(ScriptedLLM()))["answer"].startswith("No records found")


def test_sql_rules_say_totals_over_nothing_are_zero():
    from app.llm.prompts import sql_system
    assert "COALESCE(SUM(" in sql_system("MySQL", "patient")
