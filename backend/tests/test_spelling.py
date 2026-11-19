"""Trigram matching and the "did you mean ...?" check for misspelled medicine names."""

from app.search.spelling import suggest_drug_spelling
from app.search.trigram import similarity

DRUGS = ["metformin er 500 mg", "metoprolol succinate", "lisinopril", "losartan potassium", "amoxicillin",
         "amoxicillin and clavulanate potassium", "insulin human", "naproxen", "warfarin sodium", "ibuprofen"]


def test_similarity_basics():
    assert similarity("metformin", "metformin") == 1.0
    assert similarity("Metformin", "metformin") == 1.0       # case doesn't matter
    assert 0.4 <= similarity("metfromin", "metformin") < 1.0  # a swapped pair of letters
    assert similarity("warnings", "warfarin") < 0.3           # different words stay apart
    assert similarity("", "metformin") == 0.0


def test_one_close_match_asks_yes_or_no():
    s = suggest_drug_spelling("What are the side effects of metfromin?", DRUGS)
    assert s.word == "metfromin" and s.options == ["metformin"]
    assert s.question == "Did you mean metformin?"
    assert s.option_questions == {"Yes": "What are the side effects of metformin?", "No": ""}


def test_several_close_matches_offer_up_to_three():
    s = suggest_drug_spelling("Can I take amoxicilin with my other pills?", DRUGS + ["ampicillin", "amoxapine"])
    assert s.options[0] == "amoxicillin" and 2 <= len(s.options) <= 3
    assert s.question.startswith("Did you mean one of these:") and "amoxicillin" in s.question
    assert s.option_questions["Amoxicillin"] == "Can I take amoxicillin with my other pills?"
    assert s.option_questions["None of these"] == ""


def test_correct_spelling_and_ordinary_words_are_left_alone():
    assert suggest_drug_spelling("What are the side effects of metformin?", DRUGS) is None
    assert suggest_drug_spelling("Does lisinopril interact with ibuprofen?", DRUGS) is None
    assert suggest_drug_spelling("What are the warnings and interactions for my medications?", DRUGS) is None
    assert suggest_drug_spelling("Is it safe to take during pregnancy?", DRUGS) is None


def test_salt_and_form_words_are_never_suggested():
    # "sodium" / "potassium" are parts of names, not medicines on their own.
    assert suggest_drug_spelling("How much sodum is in it?", DRUGS) is None


def test_capitalised_and_trailing_punctuation():
    s = suggest_drug_spelling("Lisinoprl side effects!", DRUGS)
    assert s.options == ["lisinopril"] and s.option_questions["Yes"] == "lisinopril side effects!"
