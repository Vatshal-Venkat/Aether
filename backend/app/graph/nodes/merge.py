"""Steps: NEXT STEP and MERGE — move on to step 2, then put the two answers together.

Plain English:
  * NEXT STEP files the finished step's result away. If the plan has another step, we go back
    round the loop for it — unless step 1 found nothing, in which case there is nothing to look
    up and we skip straight to the answer ("No records found").
  * MERGE lines the two results up side by side, like matching two lists on a shared id
    (a "left join"): each row of step 1 (e.g. doctor id d1, 19 patients) gets the matching
    columns of step 2 (e.g. name "Dr Smith"). Step 1's order is kept, so a ranking stays a ranking.
    If step 2 returned an overall total instead of one row per item, that total is the answer.
"""

from app.graph.deps import Deps
from app.graph.state import ChatState, QueryResult, StepResult
from app.graph.timing import timed


def _index(columns: list[str], name: str) -> int | None:
    lowered = [c.lower() for c in columns]
    return lowered.index(name.lower()) if name.lower() in lowered else None


def merge_results(left: QueryResult, right: QueryResult, left_key: str, right_key: str, cap: int) -> QueryResult:
    """Left join `left` to `right` on left_key = right_key, keeping left's row order."""
    li, ri = _index(left.columns, left_key), _index(right.columns, right_key)
    if ri is None or li is None:
        if len(left.rows) == 1 and len(right.rows) == 1:
            # Both steps produced one summary row (e.g. "paid per visits" and "paid per claims"):
            # keep both side by side, so the answer can state both instead of hiding one.
            return QueryResult(columns=list(left.columns) + list(right.columns), rows=[left.rows[0] + right.rows[0]],
                               total_rows=1, truncated=left.truncated or right.truncated)
        # Step 2 aggregated over the filtered rows: its result is the answer. If step 1 was cut off
        # at the row cap, step 2 only saw some of the ids — so the total is partial (final review).
        return right.model_copy(update={"truncated": right.truncated or left.truncated})
    keep = [i for i in range(len(right.columns)) if i != ri]
    taken = {c.lower() for c in left.columns}
    extra = []
    for i in keep:
        name = right.columns[i]
        extra.append(f"{name}_2" if name.lower() in taken else name)
    matches: dict[str, list[list]] = {}
    for row in right.rows:
        matches.setdefault(str(row[ri]), []).append([row[i] for i in keep])
    rows = []
    for row in left.rows:
        for found in matches.get(str(row[li]), [[None] * len(keep)]):
            rows.append(list(row) + found)
    return QueryResult(
        columns=list(left.columns) + extra,
        rows=rows[:cap],
        total_rows=min(len(rows), cap),
        truncated=left.truncated or right.truncated or len(rows) > cap,
    )


@timed("next_step")
def next_step(state: ChatState, deps: Deps) -> dict:
    done = StepResult(db=state["db"], sql=state["final_sql"], result=state["result"], sources=state.get("sources") or [])
    step_results = [*(state.get("step_results") or []), done]
    step = state.get("step", 0) + 1
    update = {"step_results": step_results, "step": step}
    plan = state.get("plan") or []
    if step < len(plan) and done.result.total_rows > 0:
        update |= {"db": plan[step].db, "final_sql": None, "result": None}
    return update


@timed("merge")
def merge(state: ChatState, deps: Deps) -> dict:
    results = state["step_results"]
    sources = list(dict.fromkeys(s for r in results for s in r.sources))
    if len(results) == 1:
        return {"result": results[0].result, "sources": sources}
    link = state["link"]
    merged = merge_results(results[0].result, results[1].result, link.from_column, link.to_column,
                           deps.settings.rows_stored_cap)
    return {"result": merged, "sources": sources}
