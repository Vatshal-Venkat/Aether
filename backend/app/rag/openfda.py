"""Fetching official FDA drug labels from openFDA.

Plain English: every medicine sold in the US comes with an official label (the leaflet in the
box). The FDA publishes them for free at api.fda.gov — no key needed for small use. For each
medicine in our patient records we ask for its label:
  1. by its RxNorm code (the standard drug number Synthea stores in medications.code);
  2. if that finds nothing, by its exact ingredient name (e.g. "AMLODIPINE").
We only ever send public drug codes and names — never anything about a patient.
Every answer (including "not found") is saved on disk, so running the build again is quick
and doesn't hit the FDA's servers a second time.

Then we keep only the sections a clinician or patient asks about: uses, dosage, warnings,
contraindications, side effects and drug interactions.
"""

import json
import re
import time
from pathlib import Path

import httpx
from pydantic import BaseModel

OPENFDA_URL = "https://api.fda.gov/drug/label.json"

# openFDA field -> the name we show in citations ("openFDA label: Lisinopril — Side effects").
SECTIONS: dict[str, str] = {
    "boxed_warning": "Boxed warning",
    "indications_and_usage": "Uses",
    "dosage_and_administration": "Dosage",
    "contraindications": "Contraindications",
    "warnings_and_cautions": "Warnings",
    "warnings": "Warnings",
    "adverse_reactions": "Side effects",
    "drug_interactions": "Drug interactions",
}


class LabelSection(BaseModel):
    drug: str            # lower-case generic name, e.g. "lisinopril"
    section: str         # display name, e.g. "Side effects"
    text: str
    rxcui: str
    set_id: str
    source_url: str      # the label on DailyMed (the NIH's public label website)
    med_description: str  # the Synthea medication that led us to this label


# Prefixes Synthea puts before the ingredient: "NDA020503 ", "24 HR ", "1 ML ", "120 ACTUAT ", "21 DAY ",
# and pill packs "{28 (norethindrone ...". Found in the first real build.
_PREFIX = re.compile(r"^(\{\s*\d+\s*\(\s*)?(NDA\d+\s+)?([\d.]+\s+(HR|ML|ACTUAT|DAY)\s+)?", re.IGNORECASE)


def ingredient_of(description: str) -> str:
    """Leading words before the first one containing a digit: 'amLODIPine 2.5 MG ...' -> 'AMLODIPINE'.
    Dose/package prefixes are skipped first: '24 HR Metformin hydrochloride 500 MG' -> 'METFORMIN HYDROCHLORIDE'."""
    words = []
    for word in _PREFIX.sub("", description.strip()).split():
        if any(ch.isdigit() for ch in word):
            break
        words.append(word)
    return " ".join(words).upper()


def _query(client: httpx.Client, search: str) -> dict | None:
    for attempt in range(2):
        response = client.get(OPENFDA_URL, params={"search": search, "limit": 1}, timeout=30)
        if response.status_code == 404:
            return None
        if response.status_code in (429, 500, 502, 503) and attempt == 0:
            time.sleep(5)
            continue
        response.raise_for_status()
        results = response.json().get("results") or []
        return results[0] if results else None
    return None


def fetch_label(client: httpx.Client, code: str, description: str, cache_dir: Path) -> dict | None:
    """The FDA label for one medicine (or None), using the on-disk cache when possible."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{code}.json"
    if cached.exists():
        data = json.loads(cached.read_text(encoding="utf-8"))
        return None if data.get("missing") else data
    label = _query(client, f'openfda.rxcui:"{code}"')
    if label is None:
        label = _query(client, f'openfda.generic_name.exact:"{ingredient_of(description)}"')
    cached.write_text(json.dumps(label if label is not None else {"missing": True}), encoding="utf-8")
    return label


def label_sections(label: dict, code: str, description: str) -> list[LabelSection]:
    names = (label.get("openfda") or {}).get("generic_name") or []
    drug = (names[0] if names else ingredient_of(description)).lower()
    set_id = label.get("set_id", "")
    url = f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={set_id}"
    # Several openFDA fields can share one display name (old-style `warnings` and newer
    # `warnings_and_cautions`): merge them into one section (a real label had both).
    texts: dict[str, list[str]] = {}
    for key, display in SECTIONS.items():
        text = re.sub(r"\s+", " ", " ".join(label.get(key) or [])).strip()
        if text:
            texts.setdefault(display, []).append(text)
    return [LabelSection(drug=drug, section=display, text=" ".join(parts), rxcui=code, set_id=set_id,
                         source_url=url, med_description=description) for display, parts in texts.items()]
