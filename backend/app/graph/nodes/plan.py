"""Step: PLAN — split a two-database question into two steps.

Plain English: some questions need both databases. "Which doctor saw the most patients, by name?"
— visits live in PostgreSQL (clinical_db), doctor names live in MySQL (billing_db). A database
can't join to another database, so we answer in two steps:

    step 1 (clinical): count patients per doctor id, keep the top one(s)
    step 2 (billing):  look up the names of THOSE doctor ids

The AI proposes the two steps and picks how they connect from a fixed list of links
(e.g. encounters.provider = providers.id). Code checks the proposal; later, code — not the AI —
carries step 1's ids into step 2. One-database questions skip the AI here entirely.
"""

from app.db.catalog import Catalog
from app.db.engines import DbName
from app.graph.deps import Deps
from app.graph.state import ChatState, Link, PlanStep, QueryPlan
from app.graph.timing import timed
from app.llm.client import LLMOutputError, ask_json
from app.llm.prompts import plan_system
from app.semantic.glossary import Glossary


def _norm_link(text: str) -> str:
    left, _, right = text.partition("=")
    return f"{left.strip().lower()} = {right.strip().lower()}"


def normalize_plan(raw: QueryPlan, databases: list[DbName], glossary: Glossary,
                   catalog: Catalog) -> tuple[list[PlanStep], Link | None]:
    """Check the AI's plan; return the steps and the link oriented from step 1 to step 2."""
    steps = raw.steps
    if not 1 <= len(steps) <= 2:
        raise LLMOutputError(f"plan must have 1 or 2 steps, got {len(steps)}")
    if len(steps) == 1:
        return steps, None
    if steps[0].db == steps[1].db:
        raise LLMOutputError("the two steps of a plan must use different databases")
    allowed = {_norm_link(l) for l in glossary.links}
    if not raw.link or _norm_link(raw.link) not in allowed:
        raise LLMOutputError(f"plan link {raw.link!r} is not one of the known links")
    left, right = (side.strip().split(".", 1) for side in _norm_link(raw.link).split("="))
    owner = {name: t.db for name, t in catalog.tables.items()}
    if owner.get(left[0]) == steps[0].db:
        first, second = left, right
    elif owner.get(right[0]) == steps[0].db:
        first, second = right, left
    else:
        raise LLMOutputError("the plan link does not touch step 1's database")
    return steps, Link(from_table=first[0], from_column=first[1], to_table=second[0], to_column=second[1])


@timed("plan")
def plan(state: ChatState, deps: Deps) -> dict:
    databases = list(dict.fromkeys(state["route"].databases or ["clinical"]))
    if (saved := state.get("saved_query")) is not None:  # asked before: the same steps as last time
        steps, link = saved.plan, saved.link
    elif len(databases) == 1:
        steps, link = [PlanStep(db=databases[0], goal=state["question"])], None
    else:
        raw = ask_json(deps.llm, plan_system(deps.glossary.links), state["question"], QueryPlan)
        steps, link = normalize_plan(raw, databases, deps.glossary, deps.catalog)
    return {"plan": steps, "link": link, "step": 0, "db": steps[0].db, "step_results": []}
