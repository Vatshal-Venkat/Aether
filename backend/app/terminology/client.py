"""Aether's MCP client for the terminology server: turn a question's condition words into official names and codes.

Plain English: before the AI writes SQL, the condition words the router found ("high blood pressure") are sent to
the terminology MCP server, and its answer ("Hypertension, ICD-10 I10, also called HTN") is added to the hints the
SQL writer reads. It connects to TERMINOLOGY_MCP_URL when set, otherwise to Aether's own server in-process.
If the server is slow or down, the question is answered without the hints.
"""

import asyncio
import logging
from functools import lru_cache

from pydantic import BaseModel

from mcp import Client

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 6.0


class TermMatch(BaseModel):
    term: str        # what the person wrote, e.g. "high blood pressure"
    name: str        # official name, e.g. "Hypertension"
    icd10cm: list[str]
    synonyms: list[str]


class TerminologyClient:
    def __init__(self, target=None):
        if target is None:
            from app.terminology.server import mcp
            target = mcp
        self.target = target  # a URL ("https://.../mcp") or an MCPServer (in-process)

    async def _lookup(self, terms: list[str]) -> list[TermMatch]:
        matches: list[TermMatch] = []
        async with Client(self.target, read_timeout_seconds=TIMEOUT_SECONDS) as client:
            for term in terms:
                result = await client.call_tool("search_conditions", {"term": term, "max_results": 1})
                found = ((result.structured_content or {}).get("result") or []) if not result.is_error else []
                matches += [TermMatch(term=term, name=c["name"], icd10cm=c["icd10cm"], synonyms=c["synonyms"][:5])
                            for c in found]
        return matches

    def lookup(self, terms: list[str]) -> list[TermMatch]:
        """Matches for these condition words; [] on any failure (runs in the pipeline's worker thread)."""
        terms = list(dict.fromkeys(t.strip() for t in terms if t and t.strip()))[:5]
        if not terms:
            return []
        try:
            return _cached(self, tuple(terms))
        except Exception:  # noqa: BLE001 — hints are a nicety; never fail a question over them
            log.warning("terminology lookup failed for %s", terms, exc_info=True)
            return []


@lru_cache(maxsize=512)
def _cached(client: TerminologyClient, terms: tuple[str, ...]) -> list[TermMatch]:
    return asyncio.run(asyncio.wait_for(client._lookup(list(terms)), TIMEOUT_SECONDS * 2))


def render_hints(matches: list[TermMatch]) -> str:
    lines = []
    for m in matches:
        codes = f" (ICD-10-CM {', '.join(m.icd10cm)})" if m.icd10cm else ""
        also = f"; also called {', '.join(m.synonyms)}" if m.synonyms else ""
        lines.append(f"- \"{m.term}\" means {m.name}{codes}{also}. Match it in description columns by these words "
                     "(e.g. ILIKE), not by ICD-10 code — the records use their own codes.")
    return "TERMINOLOGY (from the medical terminology service):\n" + "\n".join(lines) if lines else ""
