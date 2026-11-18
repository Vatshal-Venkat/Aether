"""The whole pipeline, end to end, with a scripted AI and a throwaway SQLite 'clinical' database."""

import pytest
from sqlalchemy import create_engine, text

from app.graph.runner import run_chat
from tests.fakes import ScriptedLLM, make_deps

ROUTE_SQL = '{"kind": "sql", "databases": ["clinical"], "reason": "count of patients"}'


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE patients (id TEXT, first TEXT, last TEXT, birthdate TEXT, gender TEXT)"))
        for i in range(111):
            conn.execute(text("INSERT INTO patients VALUES (:i, 'A', 'B', '1990-01-01', 'F')"), {"i": f"p{i}"})
    return engine


def _run(llm, engine, role="clinician", patient_id=None):
    deps = make_deps(llm, engines={"clinical": engine})
    return run_chat(deps, "How many patients are there?", role, patient_id, "session-1")


def test_happy_path(engine):
    llm = ScriptedLLM(ROUTE_SQL, "```sql\nSELECT count(*) AS n FROM patients\n```",
                      "There are 111 patients. Source: clinical_db.patients")
    result = _run(llm, engine)
    assert result.kind == "answer"
    assert "111" in result.answer
    assert len(result.sql) == 1
    assert result.sql[0].query == "SELECT count(*) AS n FROM patients"  # what the AI wrote
    assert result.sql[0].error is None
    assert result.sources == ["clinical_db.patients"]
    assert result.table.rows == [[111]]
    assert {"route", "inject_schema", "generate_sql", "validate", "execute", "synthesize", "verify_numbers"} <= set(result.timings)


def test_retry_then_success(engine):
    llm = ScriptedLLM(ROUTE_SQL, "SELECT cnt FROM patients", "SELECT count(*) AS n FROM patients",
                      "There are 111 patients.")
    result = _run(llm, engine)
    assert result.kind == "answer"
    assert len(result.sql) == 2
    assert "cnt" in result.sql[0].error and result.sql[1].error is None


def test_gives_up_after_three_failures(engine):
    llm = ScriptedLLM(ROUTE_SQL, "SELECT a FROM patients", "SELECT b FROM patients", "SELECT c FROM patients")
    result = _run(llm, engine)
    assert result.kind == "error" and len(result.sql) == 3


def test_refusal_path(engine):
    llm = ScriptedLLM('{"kind": "refuse", "databases": [], "reason": "other patients"}')
    result = _run(llm, engine, role="patient", patient_id="p1")
    assert result.kind == "refusal" and "your own records" in result.answer
    assert result.sql == []


def test_clinician_refusal_does_not_mention_patient_mode(engine):
    # Live test: "Delete all patients" as a clinician got the patient-mode message.
    llm = ScriptedLLM('{"kind": "refuse", "databases": [], "reason": "asks to delete data"}')
    result = _run(llm, engine, role="clinician")
    assert result.kind == "refusal"
    assert "patient mode" not in result.answer and "read" in result.answer.lower()


def test_out_of_scope_path(engine):
    llm = ScriptedLLM('{"kind": "out_of_scope", "databases": [], "reason": "weather"}')
    result = _run(llm, engine)
    assert result.kind == "out_of_scope"


def test_llm_failure_returns_error_kind(engine):
    import httpx

    result = _run(ScriptedLLM(httpx.ConnectError("connection refused")), engine)
    assert result.kind == "error"
    # A connection problem is "unavailable" — only a real rate limit may say "rate-limited"
    # (the accuracy report treats rate-limited questions as "not run").
    assert "unavailable" in result.answer and "rate-limited" not in result.answer


def test_rate_limit_is_named_as_such(engine):
    class RateLimitError(Exception):
        status_code = 429

    result = _run(ScriptedLLM(RateLimitError("Rate limit reached: tokens per day")), engine)
    assert result.kind == "error" and "rate-limited" in result.answer


def test_unusable_ai_reply_gets_its_own_message(engine):
    # Review I3: not every failure is "the AI service is down".
    result = _run(ScriptedLLM("not json", "still not json"), engine)
    assert result.kind == "error" and "rephras" in result.answer


def test_unexpected_bug_gets_generic_message(engine):
    result = _run(ScriptedLLM(RuntimeError("some bug")), engine)
    assert result.kind == "error"
    assert "rate-limited" not in result.answer and "server log" in result.answer


# --- Plan 2: billing database and two-database questions --------------------------------
@pytest.fixture
def two_dbs():
    clinical = create_engine("sqlite://")
    with clinical.begin() as conn:
        conn.execute(text("CREATE TABLE encounters (id TEXT, patient TEXT, provider TEXT)"))
        conn.execute(text("INSERT INTO encounters VALUES ('e1','p1','d1'), ('e2','p2','d1'), ('e3','p1','d2')"))
    billing = create_engine("sqlite://")
    with billing.begin() as conn:
        conn.execute(text("CREATE TABLE providers (id TEXT, name TEXT)"))
        conn.execute(text("INSERT INTO providers VALUES ('d1','Dr One'), ('d2','Dr Two'), ('d3','Dr Three')"))
        conn.execute(text("CREATE TABLE claims (id TEXT, patientid TEXT, outstandingp REAL)"))
        conn.execute(text("INSERT INTO claims VALUES ('c1','p1',10), ('c2','p1',5), ('c3','p2',99)"))
    return {"clinical": clinical, "billing": billing}


ROUTE_BOTH = '{"kind": "sql", "databases": ["clinical", "billing"], "reason": "visits + doctor names"}'
ROUTE_BILLING = '{"kind": "sql", "databases": ["billing"], "reason": "billing"}'
DOCTOR_PLAN = ('{"steps": [{"db": "clinical", "goal": "distinct patients per provider id, top 1"}, '
               '{"db": "billing", "goal": "name of that provider"}], "link": "encounters.provider = providers.id"}')
STEP1 = "SELECT provider, count(DISTINCT patient) AS n FROM encounters GROUP BY provider ORDER BY n DESC LIMIT 1"


def _ask(llm, dbs, question, role="clinician", patient_id=None):
    return run_chat(make_deps(llm, engines=dbs), question, role, patient_id, "s")


def test_billing_only_question(two_dbs):
    llm = ScriptedLLM(ROUTE_BILLING, "SELECT name FROM providers WHERE id = 'd2'",
                      "The doctor is Dr Two. Source: billing_db.providers")
    result = _ask(llm, two_dbs, "What is the name of doctor d2?")
    assert result.kind == "answer" and "Dr Two" in result.answer
    assert [r.db for r in result.sql] == ["billing"]
    assert result.sources == ["billing_db.providers"]


def test_cross_db_doctor_name(two_dbs):
    llm = ScriptedLLM(ROUTE_BOTH, DOCTOR_PLAN, STEP1, "SELECT id, name FROM providers",
                      "Dr One has seen the most patients (2). Sources: clinical_db.encounters, billing_db.providers")
    result = _ask(llm, two_dbs, "Which doctor has seen the most patients? Give the doctor's name.")
    assert result.kind == "answer", result.answer
    assert "Dr One" in result.answer and result.unverified_numbers == []
    assert [r.db for r in result.sql] == ["clinical", "billing"]
    assert "'d1'" in result.sql[1].query and "'d2'" not in result.sql[1].query  # ids carried by code
    assert result.table.columns == ["provider", "n", "name"]
    assert result.table.rows == [["d1", 2, "Dr One"]]
    assert result.sources == ["clinical_db.encounters", "billing_db.providers"]
    step2_prompt = llm.prompt_text(3)
    assert "keep only providers rows" in step2_prompt
    synth_prompt = llm.prompt_text(4)
    assert "step 1 on clinical_db" in synth_prompt and "step 2 on billing_db" in synth_prompt
    assert {"plan", "row_filter", "merge"} <= set(result.timings)


def test_cross_db_empty_first_step(two_dbs):
    empty = "SELECT provider, count(*) AS n FROM encounters WHERE provider = 'zzz' GROUP BY provider"
    llm = ScriptedLLM(ROUTE_BOTH, DOCTOR_PLAN, empty)  # no step-2 SQL, no answer-writing call scripted
    result = _ask(llm, two_dbs, "Which doctor has seen the most patients? Give the doctor's name.")
    assert result.kind == "answer" and "No records found" in result.answer
    assert len(result.sql) == 1


def test_cross_db_step1_retry_then_success(two_dbs):
    llm = ScriptedLLM(ROUTE_BOTH, DOCTOR_PLAN, "SELECT count(*) AS n FROM encounters", STEP1,
                      "SELECT id, name FROM providers", "Dr One (2 patients).")
    result = _ask(llm, two_dbs, "Which doctor has seen the most patients? Give the doctor's name.")
    assert result.kind == "answer"
    assert "Include the column provider" in result.sql[0].error
    assert [r.db for r in result.sql] == ["clinical", "clinical", "billing"]


def test_patient_billing_filtered(two_dbs):
    llm = ScriptedLLM(ROUTE_BILLING, "SELECT sum(outstandingp) AS owed FROM claims", "You still owe 15.0.")
    result = _ask(llm, two_dbs, "How much do I still owe?", role="patient", patient_id="p1")
    assert result.table.rows == [[15.0]]
    assert "patientid = 'p1'" in result.sql[0].query  # the rewritten query is what is shown


def test_invalid_plan_gives_error_kind(two_dbs):
    bad = '{"steps": [{"db": "clinical", "goal": "a"}, {"db": "billing", "goal": "b"}], "link": "nonsense"}'
    result = _ask(ScriptedLLM(ROUTE_BOTH, bad), two_dbs, "Which doctor saw most patients?")
    assert result.kind == "error"


def test_out_of_scope_mentions_billing_topics(engine):
    result = _run(ScriptedLLM('{"kind": "out_of_scope", "databases": [], "reason": "weather"}'), engine)
    assert result.kind == "out_of_scope" and "insurers" in result.answer and "doctors" in result.answer


# --- live progress for the website (SSE) ---------------------------------------------------------
from app.graph.runner import stream_chat  # noqa: E402


def test_stream_emits_progress_then_final(engine):
    llm = ScriptedLLM(ROUTE_SQL, "SELECT count(*) AS n FROM patients", "There are 111 patients.")
    events = list(stream_chat(make_deps(llm, engines={"clinical": engine}), "How many patients?", "clinician", None, "s"))
    progress = [e["data"] for e in events if e["event"] == "progress"]
    steps = [p["step"] for p in progress]
    assert steps[0] == "route"
    assert steps.index("generate_sql") < steps.index("execute") < steps.index("synthesize")
    assert next(p for p in progress if p["step"] == "execute")["db"] == "clinical"
    assert "next_step" not in steps  # internal bookkeeping steps are not reported
    final = events[-1]
    assert final["event"] == "final" and final["data"]["answer"] == "There are 111 patients."
    assert final["data"]["sql"][0]["query"] == "SELECT count(*) AS n FROM patients"


def test_stream_marks_a_retry(engine):
    llm = ScriptedLLM(ROUTE_SQL, "SELECT cnt FROM patients", "SELECT count(*) AS n FROM patients", "There are 111 patients.")
    events = list(stream_chat(make_deps(llm, engines={"clinical": engine}), "How many?", "clinician", None, "s"))
    writes = [e["data"] for e in events if e["event"] == "progress" and e["data"]["step"] == "generate_sql"]
    assert [w["retry"] for w in writes] == [False, True]


def test_stream_turns_a_crash_into_an_error_event(engine):
    import httpx
    events = list(stream_chat(make_deps(ScriptedLLM(httpx.ConnectError("down")), engines={"clinical": engine}),
                              "Hi", "clinician", None, "s"))
    assert events[-1]["event"] == "error" and "unavailable" in events[-1]["data"]["message"]


def test_result_records_the_route(engine):
    llm = ScriptedLLM(ROUTE_SQL, "SELECT count(*) AS n FROM patients", "There are 111 patients.")
    assert _run(llm, engine).route == "sql"
    assert _run(ScriptedLLM('{"kind": "refuse", "databases": [], "reason": "x"}'), engine, "patient", "p1").route == "refuse"
