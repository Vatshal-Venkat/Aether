"""The accuracy test questions, as data.

Plain English: each test question says who asks it (clinician or which patient), what kind of
reply is right (an answer, a refusal...), and how to check the answer:
  * gold SQL — a query WE wrote and trust, run with the admin account, whose values must appear
    in Aether's answer (e.g. the real count of living patients);
  * must_contain — facts that must be mentioned (for drug-label answers), as "any of these words"
    groups;
  * source_prefix — the citation that must be among the answer's documents;
  * privacy — the answer must not reveal another patient or an SSN-shaped value.
Questions about features not built yet are marked `planned` and kept out of the overall score.
If Aether asks back when an answer was expected, the test replies once, like a person would ("Yes, go ahead", or
the case's clarify_reply), and scores the answer that follows.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

QUESTIONS_PATH = Path(__file__).with_name("questions.yaml")

Category = Literal["clinical", "billing", "cross_db", "rag", "hybrid", "patient", "privacy", "safety", "conversation", "planned"]


class Gold(BaseModel):
    db: Literal["clinical", "billing"]
    sql: str  # may use :patient_id for the asking patient, and :prev (values from the previous step)
    then: "Gold | None" = None  # a second step on the other database, fed the first step's values


class EvalCase(BaseModel):
    id: str
    category: Category
    role: Literal["clinician", "patient"]
    patient: str | None = None                 # patient's display name, e.g. "Angelyn934 Harris789"
    question: str
    expect_kind: Literal["answer", "refusal", "out_of_scope", "clarification", "any"] = "answer"
    expect_route: Literal["sql", "rag", "hybrid", "clarify", "refuse", "out_of_scope", "any"] = "any"
    gold: Gold | None = None
    gold_check: Literal["all", "any"] = "all"   # every gold value must appear, or at least one
    forbid_gold: bool = False                  # the gold values must NOT appear (e.g. company totals for a patient)
    must_contain: list[list[str]] = Field(default_factory=list)  # each inner list: at least one word must appear
    must_not_contain: list[str] = Field(default_factory=list)
    source_prefix: str | None = None
    privacy: bool = False
    planned: str | None = None                 # e.g. "Plan 4": shown, but not in the overall score
    follow_up_of: str | None = None            # asked in the same conversation as that case (memory)
    clarify_reply: str | None = None           # what the asker says if Aether asks back (no "Yes, go ahead" button)
    note: str = ""


def load_cases(path: Path = QUESTIONS_PATH) -> list[EvalCase]:
    cases = [EvalCase.model_validate(c) for c in yaml.safe_load(path.read_text(encoding="utf-8"))]
    ids = [c.id for c in cases]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"duplicate case ids: {sorted(duplicates)}")
    return cases
