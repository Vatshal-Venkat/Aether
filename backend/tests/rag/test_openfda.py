"""Fetching FDA drug labels (openFDA) and picking out the useful sections. No real network: MockTransport."""

import json
from pathlib import Path

import httpx
import pytest

from app.rag.openfda import SECTIONS, fetch_label, ingredient_of, label_sections

FIX = Path(__file__).parents[1] / "fixtures" / "openfda"
LISINOPRIL = json.loads((FIX / "lisinopril.json").read_text())
NOT_FOUND = json.loads((FIX / "empty.json").read_text())


@pytest.mark.parametrize("desc, expected", [
    ("lisinopril 10 MG Oral Tablet", "LISINOPRIL"),
    ("amLODIPine 2.5 MG Oral Tablet", "AMLODIPINE"),
    ("insulin isophane  human 70 UNT/ML / insulin  regular  human 30 UNT/ML Injectable Suspension [Humulin]",
     "INSULIN ISOPHANE HUMAN"),
    ("Hydrochlorothiazide 25 MG Oral Tablet", "HYDROCHLOROTHIAZIDE"),
    # dose/package prefixes found in the real data (build run 1: ~45 of 152 gave an empty ingredient)
    ("24 HR Metformin hydrochloride 500 MG Extended Release Oral Tablet", "METFORMIN HYDROCHLORIDE"),
    ("1 ML Enoxaparin sodium 150 MG/ML Prefilled Syringe", "ENOXAPARIN SODIUM"),
    ("120 ACTUAT fluticasone propionate 0.044 MG/ACTUAT Metered Dose Inhaler [Flovent]", "FLUTICASONE PROPIONATE"),
    ("NDA020503 200 ACTUAT Albuterol 0.09 MG/ACTUAT Metered Dose Inhaler", "ALBUTEROL"),
    ("21 DAY ethinyl estradiol 0.000625 MG/HR / etonogestrel 0.005 MG/HR Vaginal System [NuvaRing]", "ETHINYL ESTRADIOL"),
    ("{28 (norethindrone 0.35 MG Oral Tablet) } Pack [Camila 28 Day]", "NORETHINDRONE"),
])
def test_ingredient_of(desc, expected):
    assert ingredient_of(desc) == expected


def _client(responses, seen):
    """responses: list of (status, json) returned in order; every request's search is recorded in `seen`."""
    queue = list(responses)

    def handler(request: httpx.Request):
        seen.append(request.url.params["search"])
        status, body = queue.pop(0)
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_uses_rxcui_first(tmp_path):
    seen = []
    label = fetch_label(_client([(200, LISINOPRIL)], seen), "314076", "lisinopril 10 MG Oral Tablet", tmp_path)
    assert seen == ['openfda.rxcui:"314076"']
    assert label["set_id"] == LISINOPRIL["results"][0]["set_id"]


def test_fetch_falls_back_to_exact_generic_name(tmp_path):
    seen = []
    label = fetch_label(_client([(404, NOT_FOUND), (200, LISINOPRIL)], seen), "308136",
                        "amLODIPine 2.5 MG Oral Tablet", tmp_path)
    assert seen == ['openfda.rxcui:"308136"', 'openfda.generic_name.exact:"AMLODIPINE"']
    assert label is not None


def test_fetch_miss_cached(tmp_path):
    seen = []
    client = _client([(404, NOT_FOUND), (404, NOT_FOUND)], seen)
    assert fetch_label(client, "999", "madeupdrug 5 MG", tmp_path) is None
    assert fetch_label(client, "999", "madeupdrug 5 MG", tmp_path) is None
    assert len(seen) == 2  # the second call is answered from the cache


def test_fetch_reads_cache(tmp_path):
    (tmp_path / "314076.json").write_text(json.dumps(LISINOPRIL["results"][0]))
    seen = []
    assert fetch_label(_client([], seen), "314076", "lisinopril 10 MG Oral Tablet", tmp_path) is not None
    assert seen == []


def test_label_sections():
    sections = label_sections(LISINOPRIL["results"][0], "314076", "lisinopril 10 MG Oral Tablet")
    names = {s.section for s in sections}
    assert names <= set(SECTIONS.values())
    assert {"Side effects", "Uses", "Boxed warning", "Drug interactions"} <= names
    assert all(s.drug == "lisinopril" and s.rxcui == "314076" for s in sections)
    assert all(LISINOPRIL["results"][0]["set_id"] in s.source_url for s in sections)
    assert all("  " not in s.text and s.text for s in sections)
    assert all(s.med_description == "lisinopril 10 MG Oral Tablet" for s in sections)


def test_sections_with_same_display_name_are_merged():
    # Real build crash: a label with both `warnings` and `warnings_and_cautions` produced duplicate ids.
    label = {"set_id": "s", "openfda": {"generic_name": ["X"]},
             "warnings": ["Old-style warning."], "warnings_and_cautions": ["New-style warning."]}
    sections = label_sections(label, "1", "x 5 MG Oral Tablet")
    warnings = [s for s in sections if s.section == "Warnings"]
    assert len(warnings) == 1
    assert "Old-style warning." in warnings[0].text and "New-style warning." in warnings[0].text
