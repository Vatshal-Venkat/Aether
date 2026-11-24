"""The user is told when a backup AI model answered, and when every model is out of its free allowance."""

import groq
import httpx
import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from sqlalchemy import create_engine, text

from app.graph.runner import run_chat, stream_chat
from app.llm.client import build_chain
from app.llm.usage import UsageLedger
from tests.fakes import make_deps

DAILY = ("Rate limit reached for model `{m}` on tokens per day (TPD): Limit 200000, Used 199868, "
         "Requested 1189. Please try again in {wait}.")
ROUTE = '{"kind": "sql", "databases": ["clinical"], "reason": "count"}'
MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "gemini-2.5-flash"]


def _limit(model, wait="7m36.6s"):
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com"))
    return groq.RateLimitError(DAILY.format(m=model, wait=wait), response=response, body=None)


def _model(name, replies=(), out=None):
    replies = list(replies)

    def call(messages):
        if out is not None:
            raise out
        return AIMessage(replies.pop(0), usage_metadata={"input_tokens": 9, "output_tokens": 1, "total_tokens": 10})
    return RunnableLambda(call, name=name)


@pytest.fixture
def engine():
    e = create_engine("sqlite://")
    with e.begin() as conn:
        conn.execute(text("CREATE TABLE patients (id TEXT, first TEXT, last TEXT, birthdate TEXT, gender TEXT)"))
        conn.execute(text("INSERT INTO patients VALUES ('p1','Ann1','Lee2','1990-01-01','F')"))
    return e


def _deps(engine, tmp_path, models):
    ledger = UsageLedger(tmp_path / "u.sqlite")
    deps = make_deps(build_chain(models, ledger=ledger), engines={"clinical": engine})
    deps.models, deps.usage = MODELS[: len(models)], ledger
    return deps


ANSWER = [ROUTE, "SELECT count(*) AS n FROM patients", "There is 1 patient."]


def test_no_notice_when_the_main_model_answers(engine, tmp_path):
    deps = _deps(engine, tmp_path, [_model(MODELS[0], ANSWER), _model(MODELS[1], ANSWER)])
    result = run_chat(deps, "How many patients?", "clinician", None, "s")
    assert result.kind == "answer" and result.model_notice is None


def test_notice_when_a_backup_model_answers(engine, tmp_path):
    deps = _deps(engine, tmp_path, [_model(MODELS[0], out=_limit(MODELS[0])), _model(MODELS[1], ANSWER)])
    result = run_chat(deps, "How many patients?", "clinician", None, "s")
    assert result.kind == "answer"
    assert result.model_notice == ("gpt-oss-120b has used up its free daily limit, so this answer came from the "
                                   "backup model gpt-oss-20b.")


def test_streamed_answers_carry_the_notice_too(engine, tmp_path):
    deps = _deps(engine, tmp_path, [_model(MODELS[0], out=_limit(MODELS[0])), _model(MODELS[1], ANSWER)])
    final = [e for e in stream_chat(deps, "How many patients?", "clinician", None, "s") if e["event"] == "final"][0]
    assert "backup model gpt-oss-20b" in final["data"]["model_notice"]


def test_all_models_out_says_so_and_when_the_first_is_back(engine, tmp_path):
    deps = _deps(engine, tmp_path, [_model(MODELS[0], out=_limit(MODELS[0], "11m48s")),
                                    _model(MODELS[1], out=_limit(MODELS[1], "4m2s")),
                                    _model(MODELS[2], out=_limit(MODELS[2], "30m"))])
    result = run_chat(deps, "How many patients?", "clinician", None, "s")
    assert result.kind == "error"
    assert result.answer == ("All 3 AI models (gpt-oss-120b, gpt-oss-20b, gemini-2.5-flash) are rate-limited: they "
                             "have used up their free daily allowance. The first one is back in about 5 minutes.")
    # The accuracy report counts "rate-limited" answers as "not run", not wrong (report 2026-11-23 counted 3 as wrong).
    from app.eval.scoring import RATE_LIMITED
    assert RATE_LIMITED in result.answer


# Report 2026-11-24: some answers came from the backup model and nobody could tell which. Every answer now
# lists the models that wrote it, so the accuracy report can show them.
def test_the_models_that_answered_are_recorded(engine, tmp_path):
    main = run_chat(_deps(engine, tmp_path, [_model(MODELS[0], ANSWER)]), "How many patients?", "clinician", None, "s")
    assert main.models_used == ["openai/gpt-oss-120b"]
    (tmp_path / "b").mkdir()
    backup = run_chat(_deps(engine, tmp_path / "b", [_model(MODELS[0], out=_limit(MODELS[0])), _model(MODELS[1], ANSWER)]),
                      "How many patients?", "clinician", None, "t")
    assert backup.models_used == ["openai/gpt-oss-20b"]
