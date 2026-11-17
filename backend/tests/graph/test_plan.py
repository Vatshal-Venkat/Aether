"""Routing to both databases, and the plan step that splits a two-database question in two."""

import json

import pytest

from app.graph.nodes.plan import normalize_plan, plan
from app.graph.nodes.route import route
from app.graph.state import Link, PlanStep, QueryPlan, RouteDecision, merge_dicts
from app.llm.client import LLMOutputError
from tests.fakes import ScriptedLLM, make_deps

CLINICIAN = {"role": "clinician", "patient_id": None}
Q = "Which doctor has seen the most patients? Give the doctor's name."
DOCTOR_PLAN = {
    "steps": [{"db": "clinical", "goal": "count distinct patients per provider id"},
              {"db": "billing", "goal": "names of those providers"}],
    "link": "encounters.provider = providers.id",
}


def _state(databases, question=Q):
    return {"question": question, **CLINICIAN, "route": RouteDecision(kind="sql", databases=databases)}


def test_single_db_no_llm_call():
    out = plan(_state(["billing"], "Which insurer has the most customers?"), make_deps(ScriptedLLM()))
    assert out["plan"] == [PlanStep(db="billing", goal="Which insurer has the most customers?")]
    assert out["link"] is None and out["step"] == 0 and out["db"] == "billing" and out["step_results"] == []


def test_two_db_plan():
    llm = ScriptedLLM(json.dumps(DOCTOR_PLAN))
    out = plan(_state(["clinical", "billing"]), make_deps(llm))
    assert [s.db for s in out["plan"]] == ["clinical", "billing"]
    assert out["link"] == Link(from_table="encounters", from_column="provider", to_table="providers", to_column="id")
    assert "encounters.provider = providers.id" in llm.prompt_text()  # the allowed links are shown to the AI


def _norm(raw):
    deps = make_deps(ScriptedLLM())
    return normalize_plan(QueryPlan.model_validate(raw), ["clinical", "billing"], deps.glossary, deps.catalog)


def test_link_oriented_to_first_step():
    raw = {"steps": [{"db": "billing", "goal": "a"}, {"db": "clinical", "goal": "b"}],
           "link": "encounters.provider = providers.id"}
    steps, link = _norm(raw)
    assert link == Link(from_table="providers", from_column="id", to_table="encounters", to_column="provider")


def test_link_whitespace_tolerated():
    _, link = _norm({**DOCTOR_PLAN, "link": "encounters.provider=providers.id "})
    assert link.to_table == "providers"


@pytest.mark.parametrize("raw", [
    {**DOCTOR_PLAN, "link": "encounters.patient = providers.id"},           # not an allowed link
    {**DOCTOR_PLAN, "link": None},                                          # missing
    {"steps": [{"db": "clinical", "goal": "a"}, {"db": "clinical", "goal": "b"}], "link": DOCTOR_PLAN["link"]},
    {"steps": DOCTOR_PLAN["steps"] * 2, "link": DOCTOR_PLAN["link"]},       # more than 2 steps
    {"steps": [], "link": None},
])
def test_bad_plans_rejected(raw):
    with pytest.raises(LLMOutputError):
        _norm(raw)


def test_one_step_plan_from_two_db_route_is_kept():
    steps, link = _norm({"steps": [{"db": "billing", "goal": "x"}], "link": None})
    assert [s.db for s in steps] == ["billing"] and link is None


def test_route_keeps_billing():
    llm = ScriptedLLM('{"kind": "sql", "databases": ["billing"], "reason": "insurers"}')
    out = route({"question": "Which insurer has most customers?", **CLINICIAN}, make_deps(llm))
    assert out["route"].databases == ["billing"]
    assert "billing" in llm.prompt_text()


def test_route_empty_databases_defaults_to_clinical():
    llm = ScriptedLLM('{"kind": "sql", "databases": [], "reason": ""}')
    assert route({"question": "x", **CLINICIAN}, make_deps(llm))["route"].databases == ["clinical"]


def test_merge_dicts_sums():
    assert merge_dicts({"a": 1.0, "b": 2.0}, {"a": 0.5}) == {"a": 1.5, "b": 2.0}


# --- Plan 3 live test P3: a patient naming ANOTHER patient is refused by code, before any AI call ----
NAMES = {"p1": "Angelyn934 Harris789", "p2": "Miranda712 Jacobs452"}


@pytest.mark.parametrize("question", [
    "Show me Miranda712 Jacobs452's medications.",
    "What allergies does Miranda Jacobs have?",          # digits dropped
    "list miranda712's visits",                           # one name token, any case
])
def test_patient_naming_another_patient_is_refused_without_ai(question):
    deps = make_deps(ScriptedLLM())  # no replies scripted: any AI call would fail the test
    deps.patient_names = NAMES
    out = route({"question": question, "role": "patient", "patient_id": "p1"}, deps)
    assert out["route"].kind == "refuse"


@pytest.mark.parametrize("question", [
    "What are Angelyn934 Harris789's medications?",   # her own name
    "What medications am I taking?",
    "Is Jacobson's test normal?",                      # not a name token match
])
def test_patient_own_or_no_name_goes_to_ai(question):
    deps = make_deps(ScriptedLLM('{"kind": "sql", "databases": ["clinical"], "reason": "own"}'))
    deps.patient_names = NAMES
    assert route({"question": question, "role": "patient", "patient_id": "p1"}, deps)["route"].kind == "sql"


def test_clinician_naming_patients_is_fine():
    deps = make_deps(ScriptedLLM('{"kind": "sql", "databases": ["clinical"], "reason": "x"}'))
    deps.patient_names = NAMES
    assert route({"question": "Show me Miranda712's meds", **CLINICIAN}, deps)["route"].kind == "sql"


def test_patient_asking_about_a_doctor_sharing_a_surname_is_not_refused():
    # Final review: Synthea reuses surname tokens ("Bosco882") for patients AND doctors; 63/111 patients
    # were refused when asking about one of their own doctors.
    deps = make_deps(ScriptedLLM('{"kind": "sql", "databases": ["billing"], "reason": "doctor"}'))
    deps.patient_names = {**NAMES, "p3": "Peter1 Bosco882"}
    deps.provider_names = ["Zane918 Bosco882"]
    out = route({"question": "What is Dr. Zane918 Bosco882's specialty?", "role": "patient", "patient_id": "p1"}, deps)
    assert out["route"].kind == "sql"


def test_full_name_of_patient_sharing_a_doctor_surname_still_refused():
    deps = make_deps(ScriptedLLM())
    deps.patient_names = {**NAMES, "p3": "Peter1 Bosco882"}
    deps.provider_names = ["Zane918 Bosco882"]
    out = route({"question": "Show Peter1 Bosco882's visits", "role": "patient", "patient_id": "p1"}, deps)
    assert out["route"].kind == "refuse"
