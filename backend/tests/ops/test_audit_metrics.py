"""The audit log (who asked what, what ran) and the live counters behind /metrics."""

from app.graph.runner import ChatResult, SqlRecord
from app.graph.state import QueryResult
from app.ops.audit import AuditEntry, AuditLog
from app.ops.metrics import Metrics


def entry(i, **kw):
    base = dict(role="clinician", patient_id=None, question=f"q{i}", standalone=None, route="sql", kind="answer",
                sql=[{"db": "clinical", "query": "SELECT 1", "error": None}], row_count=1, cached=False,
                status="ok", latency_s=1.5)
    return AuditEntry(**(base | kw))


def test_audit_roundtrip_newest_first(tmp_path):
    log = AuditLog(tmp_path / "a.sqlite")
    for i in range(5):
        log.record(entry(i))
    recent = log.recent(3)
    assert [e.question for e in recent] == ["q4", "q3", "q2"]
    assert recent[0].sql[0]["db"] == "clinical" and recent[0].timestamp is not None


def test_audit_entry_from_result():
    result = ChatResult(answer="x", kind="answer", route="sql",
                        sql=[SqlRecord(db="billing", query="SELECT 2", error="boom"), SqlRecord(db="billing", query="SELECT 3")],
                        table=QueryResult(columns=["n"], rows=[[1], [2]], total_rows=2, truncated=False),
                        standalone_question="full q")
    e = AuditEntry.from_result(result, role="patient", patient_id="p1", question="q", latency_s=2.0, cached=False)
    assert e.row_count == 2 and e.standalone == "full q" and e.status == "ok"
    assert [s["error"] for s in e.sql] == ["boom", None]
    assert AuditEntry.from_result(ChatResult(answer="down", kind="error"), role="clinician", patient_id=None,
                                  question="q", latency_s=0.1, cached=False).status == "error"


def test_metrics_counts_and_renders():
    m = Metrics()
    result = ChatResult(answer="x", kind="answer", sql=[SqlRecord(db="clinical", query="a", error="e"), SqlRecord(db="clinical", query="b")],
                        timings={"route": 0.5, "generate_sql": 1.0})
    m.observe(result, seconds=2.0, cached=False)
    m.observe(result, seconds=0.01, cached=True)
    m.cache_miss()
    m.rate_limited()
    text = m.render().decode()
    assert 'aether_requests_total{cached="false",kind="answer"} 1.0' in text
    assert 'aether_requests_total{cached="true",kind="answer"} 1.0' in text
    assert "aether_sql_errors_total 1.0" in text
    assert 'aether_cache_lookups_total{result="hit"} 1.0' in text
    assert 'aether_cache_lookups_total{result="miss"} 1.0' in text
    assert "aether_rate_limited_total 1.0" in text
    assert 'aether_step_seconds_count{step="generate_sql"} 1.0' in text  # cached answers don't re-count steps


def test_audit_file_is_only_created_when_first_used(tmp_path):
    # A refused request (e.g. pipeline down) built the ops kit and created data/audit.sqlite for nothing.
    log = AuditLog(tmp_path / "a.sqlite")
    assert not (tmp_path / "a.sqlite").exists()
    log.record(entry(1))
    assert (tmp_path / "a.sqlite").exists()


def test_first_audit_writes_at_the_same_time_are_all_kept(tmp_path):
    # Final review: the table was created after the engine was published -> "no such table" for racing threads.
    import threading
    log = AuditLog(tmp_path / "a.sqlite")
    threads = [threading.Thread(target=log.record, args=(entry(i),)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(log.recent(20)) == 8
