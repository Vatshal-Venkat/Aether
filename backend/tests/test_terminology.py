"""Terminology MCP server, client and inspector — with a fake NLM service (no network)."""

import asyncio

import pytest

from mcp import Client

from app.graph.nodes.inject_schema import inject_schema
from app.graph.state import RouteDecision
from app.terminology import client as term_client
from app.terminology import server
from app.terminology.client import TermMatch, TerminologyClient, render_hints
from scripts import mcp_inspect
from tests.fakes import ScriptedLLM, make_deps

CONDITIONS = {"high blood pressure": [3, ["1"], {"icd10cm_codes": ["I10"], "synonyms": [["HBP", "HTN"]]},
                                      [["Hypertension", "High blood pressure (hypertension (HTN))"]]]}
ICD10 = {"I10": [1, ["I10"], None, [["I10", "Essential (primary) hypertension"]]]}


@pytest.fixture(autouse=True)
def fake_nlm(monkeypatch):
    def get(path, params):
        table = CONDITIONS if path.startswith("conditions") else ICD10
        return table.get(params["terms"], [0, [], None, []])
    monkeypatch.setattr(server, "_get", get)
    term_client._cached.cache_clear()


def call(name, args):
    async def go():
        async with Client(server.mcp) as c:
            return (await c.call_tool(name, args)).structured_content["result"]
    return asyncio.run(go())


def test_server_tools():
    assert call("search_conditions", {"term": "high blood pressure"}) == [
        {"name": "Hypertension", "consumer_name": "High blood pressure (hypertension (HTN))", "icd10cm": ["I10"],
         "synonyms": ["HBP", "HTN"]}]
    assert call("search_conditions", {"term": "nothing"}) == []
    assert call("lookup_icd10", {"code": "i10"}) == {"code": "I10", "name": "Essential (primary) hypertension"}
    assert call("lookup_icd10", {"code": "Z99"}) is None


def test_client_lookup_and_hints():
    matches = TerminologyClient().lookup(["high blood pressure", "nothing", ""])
    assert matches == [TermMatch(term="high blood pressure", name="Hypertension", icd10cm=["I10"], synonyms=["HBP", "HTN"])]
    hints = render_hints(matches)
    assert '"high blood pressure" means Hypertension (ICD-10-CM I10); also called HBP, HTN' in hints
    assert render_hints([]) == ""


def test_client_failure_returns_nothing(monkeypatch):
    def boom(_path, _params):
        raise RuntimeError("NLM down")
    monkeypatch.setattr(server, "_get", boom)
    assert TerminologyClient().lookup(["high blood pressure"]) == []
    assert TerminologyClient("http://127.0.0.1:1/mcp").lookup(["x"]) == []  # nothing listening


def test_schema_gets_terminology_hints():
    route = RouteDecision(kind="sql", databases=["clinical"], conditions=["high blood pressure"])
    state = {"question": "How many patients have high blood pressure?", "role": "clinician", "patient_id": None,
             "route": route}
    deps = make_deps(ScriptedLLM())
    assert "TERMINOLOGY" not in inject_schema(state, deps)["schema_text"]  # off unless a client is given
    deps.terminology = TerminologyClient()
    assert "means Hypertension" in inject_schema(state, deps)["schema_text"]


def test_inspector_lists_and_calls(capsys):
    asyncio.run(mcp_inspect.main(["list"]))
    asyncio.run(mcp_inspect.main(["call", "lookup_icd10", '{"code": "I10"}']))
    out = capsys.readouterr().out
    assert "search_conditions(term: string, max_results?: integer)" in out
    assert "Essential (primary) hypertension" in out
