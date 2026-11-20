"""The accuracy report: ask Aether ~46 fixed questions and score every answer against the truth.

Plain English:
  1. Load the test questions (app/eval/questions.yaml).
  2. For each, compute the TRUE answer with our own trusted SQL on the admin account.
  3. Ask Aether the question through the real pipeline, exactly as the website would.
  4. Score by code (app/eval/scoring.py): right kind of reply? right route? true values present?
     privacy kept? No AI is used to judge.
  5. Write a dated report to docs/eval/ (markdown to read, JSON with every detail).

The free AI service has a daily allowance. If it is rate-limited we wait a minute and retry;
a question that still can't run is reported as "not run" — never as a wrong answer.

Run from backend/:  python -m scripts.run_eval                 (everything, ~5–10 minutes)
                    python -m scripts.run_eval --only CL01,XD01
                    python -m scripts.run_eval --category rag
"""

import argparse
import datetime as dt
import json
import statistics
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import create_engine, text

from app.config import get_settings
from app.eval.cases import EvalCase, load_cases
from app.eval.gold import compute_gold
from app.eval.scoring import RATE_LIMITED, CaseScore, score_case
from app.graph.runner import ChatResult

REPO = Path(__file__).resolve().parents[2]
SQL_CATEGORIES = {"clinical", "billing", "cross_db", "patient"}


def _rate_limited(r: ChatResult) -> bool:
    return r.kind == "error" and RATE_LIMITED in r.answer


def run_cases(cases: list[EvalCase], ask: Callable[[EvalCase, str], ChatResult], gold: Callable[[EvalCase], list],
              other_names: Callable[[EvalCase], list[str]], pause: float = 3.0, wait: float = 65.0,
              max_retries: int = 2, sleep: Callable[[float], None] = time.sleep,
              progress: Callable[[str], None] = lambda s: None) -> list[CaseScore]:
    sessions: dict[str, str] = {}
    scores: list[CaseScore] = []
    for i, case in enumerate(cases, 1):
        session = sessions.get(case.follow_up_of or "", str(uuid.uuid4()))
        sessions[case.id] = session
        result = ask(case, session)
        for _ in range(max_retries):
            if not _rate_limited(result):
                break
            progress(f"  {case.id}: rate-limited, waiting {wait:.0f} s…")
            sleep(wait)
            result = ask(case, session)
        score = score_case(case, result, gold(case) if case.gold else [], other_names(case))
        score.timings = dict(result.timings)
        scores.append(score)
        mark = "NOT RUN" if score.not_run else ("ok" if score.correct else "WRONG")
        progress(f"[{i}/{len(cases)}] {case.id:5} {mark:7} {score.seconds:5.1f}s  {'; '.join(score.reasons)[:90]}")
        if i < len(cases):
            sleep(pause)
    return scores


def _pct(a: int, b: int) -> str:
    return f"{round(100 * a / b)}%" if b else "—"


def render_report(scores: list[CaseScore], meta: dict) -> str:
    scored = [s for s in scores if not s.planned and not s.not_run]
    correct = sum(s.correct for s in scored)
    lines = [f"# Aether accuracy report — {meta['started']}", "",
             f"Model: `{meta['model']}` · questions: {len(scores)} "
             f"({len(scored)} scored, {sum(s.not_run for s in scores)} not run, "
             f"{sum(bool(s.planned) for s in scores)} planned features)", "",
             f"## Overall: **{correct} / {len(scored)} correct ({_pct(correct, len(scored))})**", ""]

    sql = [s for s in scored if s.category in SQL_CATEGORIES]
    routed = [s for s in scored if s.route_checked]  # questions that accept any route are not counted
    privacy = [s for s in scored if s.privacy]
    secs = sorted(s.seconds for s in scored if s.seconds)
    p95 = secs[min(len(secs) - 1, int(0.95 * len(secs)))] if secs else 0
    lines += ["| Measure | Result | Target (design §12) |", "|---|---|---|",
              f"| Database questions answered correctly | {sum(s.correct for s in sql)} / {len(sql)} ({_pct(sum(s.correct for s in sql), len(sql))}) | ≥ 75% |",
              f"| Routed the right way | {sum(s.route_ok for s in routed)} / {len(routed)} ({_pct(sum(s.route_ok for s in routed), len(routed))}) | ≥ 90% |",
              f"| Privacy checks held | {sum(bool(s.privacy_ok) for s in privacy)} / {len(privacy)} | all |",
              f"| Typical answer time (median / slowest 5%) | {statistics.median(secs) if secs else 0:.1f} s / {p95:.1f} s | under ~10 s |",
              f"| Questions that needed a SQL retry | {sum(1 for s in scored if s.retries)} | — |",
              f"| Answers with unmatched numbers | {sum(1 for s in scored if s.unverified)} | — |", ""]

    lines += ["## By category", "", "| Category | Correct | Ran | % |", "|---|---|---|---|"]
    for cat in dict.fromkeys(s.category for s in scored):
        group = [s for s in scored if s.category == cat]
        ok = sum(s.correct for s in group)
        lines.append(f"| {cat} | {ok} | {len(group)} | {_pct(ok, len(group))} |")

    steps: dict[str, list[float]] = {}
    for s in scored:
        for step, t in s.timings.items():
            steps.setdefault(step, []).append(t)
    if steps:
        lines += ["", "## Time per step (median)", "", "| Step | Median | Times run |", "|---|---|---|"]
        for step, ts in sorted(steps.items(), key=lambda kv: -statistics.median(kv[1])):
            lines.append(f"| {step} | {statistics.median(ts):.2f} s | {len(ts)} |")

    wrong = [s for s in scored if not s.correct]
    lines += ["", "## Wrong answers", ""]
    if not wrong:
        lines.append("None.")
    for s in wrong:
        lines.append(f"- **{s.id}** ({s.category}) — {s.question}  ")
        lines.append(f"  Why: {'; '.join(s.reasons) or 'see JSON'}  ")
        if not s.privacy:  # answers to privacy-checked questions are never copied into the report
            lines.append(f"  Answer: {' '.join(s.answer.split())[:220]}")
    not_run = [s for s in scores if s.not_run]
    if not_run:
        lines += ["", "## Not run (free AI tier rate-limited)", "", ", ".join(s.id for s in not_run)]
    planned = [s for s in scores if s.planned]
    if planned:
        lines += ["", "## Planned features (shown, not scored)", ""]
        for s in planned:
            lines.append(f"- **{s.id}** ({s.planned}) — {s.question} → {'works already' if s.correct else 'not yet'}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="comma-separated case ids")
    parser.add_argument("--category")
    parser.add_argument("--pause", type=float, default=3.0, help="seconds between questions (free-tier pacing)")
    parser.add_argument("--out", default=str(REPO / "docs" / "eval"))
    args = parser.parse_args(argv)

    from app.graph.runner import build_deps, run_chat  # imported here: building deps connects to everything

    cases = load_cases()
    if args.only:
        wanted = set(args.only.split(","))
        wanted |= {c.follow_up_of for c in cases if c.id in wanted and c.follow_up_of}  # a follow-up needs its first question
        cases = [c for c in cases if c.id in wanted]  # file order kept
    if args.category:
        cases = [c for c in cases if c.category == args.category]

    s = get_settings()
    admin = {"clinical": create_engine(s.clinical_url(admin=True)), "billing": create_engine(s.billing_url(admin=True))}
    with admin["clinical"].connect() as conn:
        people = {f"{first} {last}": pid for pid, first, last in conn.execute(text("SELECT id, first, last FROM patients"))}
    # The accuracy test measures the AI writing SQL fresh: no saved queries are reused or saved.
    deps = build_deps(s.model_copy(update={"saved_queries": False}))
    model = {"groq": s.groq_model, "gemini": s.gemini_model, "ollama": s.ollama_model}[s.llm_provider]
    started = dt.datetime.now()

    def pid(c: EvalCase) -> str | None:
        return people[c.patient] if c.patient else None

    scores = run_cases(
        cases,
        ask=lambda c, session: run_chat(deps, c.question, c.role, pid(c), session),
        gold=lambda c: compute_gold(c.gold, admin, pid(c)),
        # privacy: names of everyone except the asking patient (clinicians: only SSNs are checked)
        other_names=lambda c: [n for n in people if n != c.patient] if c.privacy and c.role == "patient" else [],
        pause=args.pause,
        progress=print,
    )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{started:%Y-%m-%d-%H%M}-{s.llm_provider}-{model.replace('/', '_')}"
    meta = {"model": f"{s.llm_provider} / {model}", "started": f"{started:%Y-%m-%d %H:%M}"}
    (out / f"{stem}.md").write_text(render_report(scores, meta), encoding="utf-8")
    raw = [sc.model_dump() | ({"answer": "(privacy question: not stored)"} if sc.privacy else {})
           for sc in scores]
    (out / f"{stem}.json").write_text(json.dumps({"meta": meta, "scores": raw}, indent=1, default=str), encoding="utf-8")
    print(f"\nReport: {out / (stem + '.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
