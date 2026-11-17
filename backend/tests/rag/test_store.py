"""The drug-label store: passages saved in ChromaDB, searched by meaning, filtered by drug."""

import json
from pathlib import Path

import pytest

from app.rag.openfda import label_sections
from app.rag.store import Chunk, DrugLabelStore
from tests.fakes import FakeEmbedding

FIX = Path(__file__).parents[1] / "fixtures" / "openfda"
LIS = label_sections(json.loads((FIX / "lisinopril.json").read_text())["results"][0], "314076", "lisinopril 10 MG Oral Tablet")
INS_DESC = "insulin isophane  human 70 UNT/ML / insulin  regular  human 30 UNT/ML Injectable Suspension [Humulin]"
INS = label_sections(json.loads((FIX / "insulin.json").read_text())["results"][0], "106892", INS_DESC)


@pytest.fixture
def store(tmp_path):
    s = DrugLabelStore.create(tmp_path / "chroma", embedding_function=FakeEmbedding())
    s.add(LIS + INS)
    return s


def test_add_and_count(store):
    assert store.count() >= len(LIS) + len(INS)


def test_search_filtered_by_drug(store):
    chunks = store.search("side effects adverse reactions", ["insulin human"], k=3)
    assert chunks and {c.drug for c in chunks} == {"insulin human"}
    assert all(isinstance(c, Chunk) for c in chunks)


def test_search_unfiltered(store):
    assert len(store.search("hypoglycemia", None, k=4)) == 4


def test_open_missing_returns_none(tmp_path):
    assert DrugLabelStore.open(tmp_path / "nothing-here", embedding_function=FakeEmbedding()) is None


def test_reopen_persists(store, tmp_path):
    reopened = DrugLabelStore.open(tmp_path / "chroma", embedding_function=FakeEmbedding())
    assert reopened is not None and reopened.count() == store.count()


def test_drug_names(store):
    assert set(store.drug_names()) == {"lisinopril", "insulin human"}


@pytest.mark.parametrize("text, expected", [
    ("lisinopril 10 MG Oral Tablet", ["lisinopril"]),
    ("What are the side effects of Lisinopril?", ["lisinopril"]),
    (INS_DESC, ["insulin human"]),                          # exact Synthea description
    ("Does insulin human interact with lisinopril?", ["insulin human", "lisinopril"]),
    ("What are the side effects of insulin?", ["insulin human"]),   # first word, when unique
    ("What about aspirin?", []),
])
def test_drugs_in_text(store, text, expected):
    assert store.drugs_in_text(text) == expected


def test_chunk_label_format():
    c = Chunk(text="x", drug="lisinopril", section="Side effects", source_url="u", distance=0.1)
    assert c.label == "openFDA label: Lisinopril — Side effects"


# --- final review: the first-word shortcut must only apply when the rest is a salt/form word ---------
def _named(*names_and_descs):
    from app.rag.openfda import LabelSection
    return [LabelSection(drug=n, section="Side effects", text=f"{n} may cause headache.", rxcui=str(i), set_id="s",
                         source_url="u", med_description=d) for i, (n, d) in enumerate(names_and_descs)]


@pytest.fixture
def wide_store(tmp_path):
    s = DrugLabelStore.create(tmp_path / "w", embedding_function=FakeEmbedding())
    s.add(_named(("sodium fluoride", "sodium fluoride 0.0272 MG/MG Oral Gel"),
                 ("estradiol valerate and estradiol valerate/dienogest", "Natazia pack"),
                 ("penicillin v potassium", "Penicillin V Potassium 250 MG Oral Tablet"),
                 ("vitamin", "1 ML Cyanocobalamin 1 MG/ML Injection"),
                 ("insulin human", INS_DESC), ("metformin er 500 mg", "24 HR Metformin hydrochloride 500 MG"),
                 ("heparin sodium", "1 ML heparin sodium  porcine 5000 UNT/ML Injection"),
                 ("lisinopril", "lisinopril 10 MG Oral Tablet")))
    return s


@pytest.mark.parametrize("text, expected", [
    ("side effects of sodium bicarbonate", []),
    ("Is estradiol safe?", []),
    ("What is the dose of penicillin G?", []),
    ("Is vitamin D safe with lisinopril?", ["lisinopril"]),          # 'vitamin' is too generic a name
    ("What are the side effects of insulin?", ["insulin human"]),     # alias kept: 'human' is a form word
    ("metformin side effects", ["metformin er 500 mg"]),
    ("heparin sodium  porcine 100 UNT/ML Injectable Solution", ["heparin sodium"]),  # not + sodium fluoride
    ("24 hr metformin hydrochloride 500 mg", ["metformin er 500 mg"]),  # lower-cased description
])
def test_drug_matching_is_not_over_eager(wide_store, text, expected):
    assert wide_store.drugs_in_text(text) == expected
