"""Aether's terminology MCP server: everyday medical words -> official condition names and ICD-10-CM codes.

Plain English: people say "high blood pressure"; records say "Hypertension". This server looks words up in the
US National Library of Medicine's free Clinical Tables service (no key needed) and returns the official name,
ICD-10-CM codes and synonyms. It only ever receives medical words — never anything about a patient.

Run on its own:   python -m app.terminology.server            (HTTP on http://127.0.0.1:8765/mcp)
                  python -m app.terminology.server --stdio    (for Claude Desktop / Claude Code)
The backend also serves it at /mcp and uses it in-process (app/terminology/client.py).
"""

import argparse

import httpx
from pydantic import BaseModel

from mcp.server.mcpserver import MCPServer

NLM = "https://clinicaltables.nlm.nih.gov/api"
TIMEOUT = 8.0


class Condition(BaseModel):
    name: str                 # clinical name, e.g. "Hypertension"
    consumer_name: str        # everyday name, e.g. "High blood pressure (hypertension (HTN))"
    icd10cm: list[str]        # e.g. ["I10"]
    synonyms: list[str]


class Icd10Code(BaseModel):
    code: str                 # e.g. "E11.9"
    name: str                 # e.g. "Type 2 diabetes mellitus without complications"


def _get(path: str, params: dict) -> list:
    response = httpx.get(f"{NLM}/{path}", params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def search_conditions_nlm(term: str, max_results: int) -> list[Condition]:
    _total, _ids, extra, display = _get("conditions/v3/search", {
        "terms": term, "df": "primary_name,consumer_name", "ef": "icd10cm_codes,synonyms", "maxList": max_results})
    extra = extra or {}
    codes, synonyms = extra.get("icd10cm_codes") or [], extra.get("synonyms") or []
    return [Condition(name=d[0], consumer_name=d[1],
                      icd10cm=[c for c in (codes[i] or "").split(",") if c] if i < len(codes) else [],
                      synonyms=list(synonyms[i] or []) if i < len(synonyms) else [])
            for i, d in enumerate(display)]


def search_icd10_nlm(term: str, max_results: int) -> list[Icd10Code]:
    _total, _codes, _extra, display = _get("icd10cm/v3/search", {"sf": "code,name", "terms": term,
                                                                "maxList": max_results})
    return [Icd10Code(code=d[0], name=d[1]) for d in display]


mcp = MCPServer(
    "aether-terminology",
    instructions="Look up medical condition names and ICD-10-CM codes (US National Library of Medicine). "
                 "Send medical words only, never patient details.",
)


@mcp.tool()
def search_conditions(term: str, max_results: int = 3) -> list[Condition]:
    """Find conditions matching an everyday or clinical phrase ("high blood pressure", "heart attack"):
    official name, everyday name, ICD-10-CM codes and synonyms."""
    return search_conditions_nlm(term, max(1, min(max_results, 10)))


@mcp.tool()
def search_icd10(term: str, max_results: int = 5) -> list[Icd10Code]:
    """Search ICD-10-CM diagnosis codes by words or by code prefix ("type 2 diabetes", "E11")."""
    return search_icd10_nlm(term, max(1, min(max_results, 20)))


@mcp.tool()
def lookup_icd10(code: str) -> Icd10Code | None:
    """The official name of one ICD-10-CM code ("I10" -> "Essential (primary) hypertension"), or null."""
    want = code.strip().upper()
    return next((c for c in search_icd10_nlm(want, 20) if c.code.upper() == want), None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stdio", action="store_true", help="talk over stdin/stdout instead of HTTP")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.stdio:
        mcp.run("stdio")
    else:
        mcp.run("streamable-http", port=args.port)


if __name__ == "__main__":
    main()
