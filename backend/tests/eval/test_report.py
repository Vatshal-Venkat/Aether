"""The runner (retries, sessions) and the markdown report — no real AI or database involved."""

from app.eval.cases import EvalCase
from app.eval.scoring import CaseScore
from app.graph.runner import ChatResult
from scripts.run_eval import render_report, run_cases

RATE = ChatResult(answer="The AI service is unavailable or rate-limited right now. Please try again in a minute.", kind="error")


def case(id_, **kw):
    return EvalCase(**({"id": id_, "category": "clinical", "role": "clinician", "question": f"q {id_}",
                        "expect_route": "sql", "gold": {"db": "clinical", "sql": "SELECT 1"}} | kw))


def test_rate_limited_is_retried_after_a_wait_then_scored():
    replies = [RATE, ChatResult(answer="99 patients.", kind="answer", route="sql", timings={"route": 1.0})]
    waits = []
    scores = run_cases([case("A")], ask=lambda c, s: replies.pop(0), gold=lambda c: [[99]],
                       other_names=lambda c: [], pause=0, wait=65, sleep=waits.append)
    assert scores[0].correct and not scores[0].not_run
    assert 65 in waits


def test_still_rate_limited_after_retries_is_not_run():
    scores = run_cases([case("A")], ask=lambda c, s: RATE, gold=lambda c: [[99]], other_names=lambda c: [],
                       pause=0, wait=1, sleep=lambda s: None, max_retries=2)
    assert scores[0].not_run and not scores[0].correct


def test_follow_up_shares_the_conversation():
    sessions = {}
    def ask(c, session):
        sessions[c.id] = session
        return ChatResult(answer="8", kind="answer", route="sql")
    run_cases([case("A"), case("B", follow_up_of="A")], ask=ask, gold=lambda c: [[8]], other_names=lambda c: [],
              pause=0, sleep=lambda s: None)
    assert sessions["A"] == sessions["B"]


def _score(id_, category, correct, **kw):
    return CaseScore(**({"id": id_, "category": category, "question": f"q {id_}", "correct": correct,
                         "kind_ok": True, "route_ok": True, "seconds": 2.0} | kw))


def test_report_per_category_and_overall_excludes_planned_and_not_run():
    scores = [_score("C1", "clinical", True), _score("C2", "clinical", False, reasons=["missing true value(s): 8"]),
              _score("B1", "billing", True), _score("N1", "clinical", False, not_run=True),
              _score("P1", "planned", False, planned="Plan 4")]
    md = render_report(scores, {"model": "groq / test-model", "started": "2026-11-18 10:00"})
    assert "| clinical | 1 | 2 | 50% |" in md
    assert "| billing | 1 | 1 | 100% |" in md
    assert "**2 / 3 correct (67%)**" in md      # planned and not-run excluded
    assert "missing true value(s): 8" in md
    assert "Not run" in md and "N1" in md
    assert "Plan 4" in md


def test_report_never_prints_privacy_answers():
    s = _score("PV1", "privacy", False, privacy=True, privacy_ok=False,
               reasons=["other patient visible (1 name(s))"], answer="Miranda712 takes X")
    md = render_report([s], {"model": "m", "started": "t"})
    assert "Miranda712" not in md and "other patient visible" in md


def test_routing_counts_only_cases_with_an_expected_route():
    scores = [_score("A", "clinical", True, route_checked=True), _score("B", "privacy", True, route_checked=False)]
    md = render_report(scores, {"model": "m", "started": "t"})
    assert "| Routed the right way | 1 / 1 (100%)" in md


def test_answers_of_any_privacy_flagged_case_are_never_printed():
    s = _score("SF3", "safety", False, privacy=True, privacy_ok=False, reasons=["SSN-shaped value visible"], answer="999-12-3456")
    md = render_report([s], {"model": "m", "started": "t"})
    assert "999-12-3456" not in md
