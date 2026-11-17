"""Answer writing (synthesize) and the number check that follows it (verify_numbers)."""

from app.graph.nodes.synthesize import synthesize
from app.graph.nodes.verify_numbers import verify_numbers
from app.graph.state import QueryResult
from tests.fakes import ScriptedLLM, make_deps


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


def test_synthesize_uses_rows_and_sources_in_prompt():
    llm = ScriptedLLM("There are 111 patients (source: clinical_db.patients).")
    out = synthesize(_state([[111]]), make_deps(llm))
    assert out["answer"].startswith("There are 111 patients")
    prompt = llm.prompt_text()
    assert "111" in prompt and "clinical_db.patients" in prompt


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
