"""The service layer around the pipeline: cache, result pages, audit, metrics, concurrency."""

import threading
import time

from app.graph.runner import ChatResult
from app.graph.state import QueryResult
from app.memory.store import ConversationStore, Turn
from app.ops import Ops
from app.service import ChatService
from tests.fakes import ScriptedLLM, make_deps


def ops(tmp_path, **kw):
    return Ops.for_tests(tmp_path, **kw)


def answer(text="There are 111 patients.", rows=1):
    table = QueryResult(columns=["n"], rows=[[i] for i in range(rows)], total_rows=rows, truncated=False)
    return ChatResult(answer=text, kind="answer", route="sql", table=table, timings={"route": 0.1})


def counting_runner(result):
    calls = []
    def run(deps, question, role, patient_id, session_id):
        calls.append((question, role, patient_id))
        return result.model_copy(deep=True)
    run.calls = calls
    return run


def svc(tmp_path, memory=None, **kw):
    deps = make_deps(ScriptedLLM(), memory=memory)
    return ChatService(deps, ops(tmp_path, **kw))


def test_repeat_question_comes_from_cache(tmp_path):
    s = svc(tmp_path)
    run = counting_runner(answer())
    first = s.answer("How many patients?", "clinician", None, "s1", runner=run)
    again = s.answer("  how many PATIENTS? ", "clinician", None, "s2", runner=run)
    assert len(run.calls) == 1 and not first.cached and again.cached and again.answer == first.answer


def test_cache_scoped_to_role_and_patient(tmp_path):
    s = svc(tmp_path)
    run = counting_runner(answer("Your medications..."))
    s.answer("What medications am I taking?", "patient", "p1", "s1", runner=run)
    s.answer("What medications am I taking?", "patient", "p2", "s2", runner=run)
    s.answer("What medications am I taking?", "clinician", None, "s3", runner=run)
    assert len(run.calls) == 3


def test_followups_bypass_cache(tmp_path):
    memory = ConversationStore(tmp_path / "m.sqlite")
    memory.add(Turn(session_id="s1", role="clinician", patient_id=None, question="q", standalone="q", answer="a", kind="answer"))
    s = svc(tmp_path, memory=memory)
    run = counting_runner(answer())
    s.answer("How many of them?", "clinician", None, "s1", runner=run)
    s.answer("How many of them?", "clinician", None, "s1", runner=run)
    assert len(run.calls) == 2


def test_only_answers_are_cached(tmp_path):
    s = svc(tmp_path)
    run = counting_runner(ChatResult(answer="The AI service is unavailable right now.", kind="error"))
    s.answer("Hi", "clinician", None, "s", runner=run)
    s.answer("Hi", "clinician", None, "s", runner=run)
    assert len(run.calls) == 2


def test_cache_hit_is_audited_and_remembered(tmp_path):
    memory = ConversationStore(tmp_path / "m.sqlite")
    s = svc(tmp_path, memory=memory)
    run = counting_runner(answer())
    s.answer("How many patients?", "clinician", None, "s1", runner=run)
    s.answer("How many patients?", "clinician", None, "s2", runner=run)
    audit = s.ops.audit.recent(5)
    assert [e.cached for e in audit] == [True, False]
    assert [t.question for t in memory.turns("s2")] == ["How many patients?"]  # the hit joined s2's conversation


def test_big_tables_come_in_pages(tmp_path):
    s = svc(tmp_path)
    result = s.answer("List encounters", "clinician", None, "s", runner=counting_runner(answer(rows=250)))
    assert len(result.table.rows) == 100 and result.table.total_rows == 250 and result.table.result_id
    page = s.ops.results.page(result.table.result_id, 3, owner=("clinician", None))
    assert len(page["rows"]) == 50


def test_stream_hit_and_miss(tmp_path):
    s = svc(tmp_path)
    def streamer(deps, question, role, patient_id, session_id):
        yield {"event": "progress", "data": {"step": "route"}}
        yield {"event": "final", "data": answer(rows=150).model_dump()}
    first = list(s.stream("q", "clinician", None, "s", streamer=streamer))
    assert first[0]["event"] == "progress" and len(first[-1]["data"]["table"]["rows"]) == 100
    second = list(s.stream("q", "clinician", None, "s", streamer=streamer))
    assert len(second) == 1 and second[0]["data"]["cached"] is True


def test_concurrency_is_capped(tmp_path):
    s = svc(tmp_path, max_concurrent_chats=2)
    running, peak, lock = [0], [0], threading.Lock()
    def slow(deps, question, role, patient_id, session_id):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.15)
        with lock:
            running[0] -= 1
        return ChatResult(answer="x", kind="error")
    threads = [threading.Thread(target=s.answer, args=(f"q{i}", "clinician", None, "s"), kwargs={"runner": slow}) for i in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert peak[0] == 2


def test_temporary_problems_are_not_cached(tmp_path):
    # Final review: "Drug information isn't loaded yet" (kind answer) stayed cached after building the library.
    from app.graph.nodes.synthesize import NO_INDEX
    s = svc(tmp_path)
    run = counting_runner(ChatResult(answer=NO_INDEX, kind="answer"))
    s.answer("Side effects of metformin?", "clinician", None, "s", runner=run)
    s.answer("Side effects of metformin?", "clinician", None, "s", runner=run)
    assert len(run.calls) == 2


def test_clinician_patient_id_is_ignored(tmp_path):
    # Final review: a clinician request that also sent patient_id stored its table under ("clinician", "p1"),
    # so the results route (which looks up ("clinician", None)) said 404.
    s = svc(tmp_path)
    result = s.answer("List", "clinician", "p1", "s", runner=counting_runner(answer(rows=150)))
    assert s.ops.results.page(result.table.result_id, 2, owner=("clinician", None)) is not None


def test_semantic_cache_hit_for_reworded_question(tmp_path):
    from app.graph.state import RouteDecision
    from app.memory.saved_queries import SavedQuery, SavedQueryStore

    class FakeEmbed:
        def __call__(self, texts):
            out = []
            for t in texts:
                s = 1.0 if "how many patients have diabetes" in t.lower() else 0.88
                out.append([s, (1 - s * s) ** 0.5])
            return out

    sq = SavedQueryStore(tmp_path / "sq.sqlite", "v1", FakeEmbed())
    sq.save("clinician", "How many patients have diabetes?", SavedQuery(route=RouteDecision(kind="sql", databases=["clinical"]), plan=[], sql=[]))

    deps = make_deps(ScriptedLLM(), saved_queries=sq)
    s = ChatService(deps, ops(tmp_path))
    run = counting_runner(answer("There are 8 patients with diabetes."))

    first = s.answer("How many patients have diabetes?", "clinician", None, "s1", runner=run)
    assert len(run.calls) == 1 and not first.cached

    again = s.answer("Number of diabetic patients", "clinician", None, "s2", runner=run)
    assert len(run.calls) == 1 and again.cached
    assert again.answer == first.answer
