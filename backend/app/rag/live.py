"""Live FDA label lookup for medicines the drug-label library doesn't have (or when it isn't built).

Plain English: instead of answering "not loaded" / "not in this library", ask openFDA for the label
right now, by the medicine's name, and use the sections the question asks about (or the main ones).
Only the public drug name is sent — never anything about a patient. Answers are cached on disk.
"""

import json
import logging
import re
from pathlib import Path

import httpx

from app.rag.chunking import chunk_text
from app.rag.openfda import OPENFDA_URL, ingredient_of, label_sections
from app.rag.store import Chunk

log = logging.getLogger(__name__)

DEFAULT_SECTIONS = ["Boxed warning", "Uses", "Side effects", "Warnings"]
PIECES_PER_SECTION = 2


def _names(label: dict, field: str) -> list[str]:
    return [n.lower() for n in (label.get("openfda") or {}).get(field) or []]


def best_label(labels: list[dict], name: str) -> dict | None:
    """The single-ingredient label for `name`: "metformin" -> METFORMIN HYDROCHLORIDE, not SITAGLIPTIN AND METFORMIN."""
    n = name.lower()

    def rank(label: dict) -> tuple[int, int]:
        generic = min(_names(label, "generic_name") or [""], key=len)
        if generic == n or n in _names(label, "brand_name"):
            return 0, len(generic)
        if generic.startswith(n) and " and " not in generic and "," not in generic:
            return 1, len(generic)
        return 2, len(generic)

    return min(labels, key=rank) if labels else None


def _search(client: httpx.Client, search: str) -> list[dict]:
    response = client.get(OPENFDA_URL, params={"search": search, "limit": 10}, timeout=10)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json().get("results") or []


def fetch_by_name(client: httpx.Client, name: str, cache_dir: Path) -> dict | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{re.sub(r'[^a-z0-9]+', '_', name.lower())}.json"
    if cached.exists():
        data = json.loads(cached.read_text(encoding="utf-8"))
        return None if data.get("missing") else data
    label = (best_label(_search(client, f'openfda.generic_name:"{name}"'), name)
             or best_label(_search(client, f'openfda.brand_name:"{name}"'), name))
    cached.write_text(json.dumps(label if label is not None else {"missing": True}), encoding="utf-8")
    return label


def live_chunks(names: list[str], sections: list[str] | None, cache_dir: Path) -> tuple[list[Chunk], list[str]]:
    """(passages from live FDA labels, names with no label found)."""
    wanted = sections or DEFAULT_SECTIONS
    chunks: list[Chunk] = []
    missing: list[str] = []
    with httpx.Client(headers={"User-Agent": "aether-learning-project"}) as client:
        for raw in names:
            name = ingredient_of(raw) or raw.upper()
            try:
                label = fetch_by_name(client, name, cache_dir)
            except httpx.HTTPError:
                log.warning("live openFDA lookup failed for %s", name, exc_info=True)
                label = None
            if label is None:
                missing.append(raw)
                continue
            for s in label_sections(label, "", raw):
                if s.section in wanted:
                    chunks += [Chunk(text=p, drug=s.drug, section=s.section, source_url=s.source_url, distance=0.0)
                               for p in chunk_text(s.text)[:PIECES_PER_SECTION]]
    return chunks, missing
