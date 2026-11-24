"""The accuracy report: ask Aether ~50 fixed questions and score every answer against the truth.

Plain English:
  1. Load the test questions (app/eval/questions.yaml).
  2. For each, compute the TRUE answer with our own trusted SQL on the admin account.
  3. Ask Aether the question through the real pipeline, exactly as the website would.
     If Aether asks back instead of answering, reply once like a person would and use the answer after that.
  4. Score by code (app/eval/scoring.py): right kind of reply? right route? true values present?
     privacy kept? No AI is used to judge.
  5. Write a dated report to docs/eval/ (markdown to read, JSON with every detail).

The free AI service has a daily allowance. If it is rate-limited we wait a minute and retry;
a question that still can't run is reported as "not run" — never as a wrong answer.

Run from backend/:  python -m scripts.run_eval                 (everything, ~5–10 minutes)
                    python -m scripts.run_eval --only CL01,XD01
                    python -m scripts.run_eval --category rag
                    python -m scripts.run_eval --only XD02,XD07 --repeat 3   (ask each 3 times: how stable is it?)
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


GO_AHEAD = "Yes, go ahead"
DEFAULT_REPLY = "Yes, use the usual meaning in the data."


def reply_to(case: EvalCase, asked: ChatResult) -> str:
    """What a person would answer to Aether's question back: click "Yes, go ahead" (the website then sends the
    question with the assumption spelled out), or say what they meant (the case's clarify_reply)."""
    if GO_AHEAD in asked.options and asked.option_questions.get(GO_AHEAD):
        return asked.option_questions[GO_AHEAD]
    return case.clarify_reply or DEFAULT_REPLY


def run_cases(cases: list[EvalCase], ask: Callable[[EvalCase, str, str], ChatResult], gold: Callable[[EvalCase], list],
              other_names: Callable[[EvalCase], list[str]], pause: float = 3.0, wait: float = 65.0,
              max_retries: int = 2, sleep: Callable[[float], None] = time.sleep,
              progress: Callable[[str], None] = lambda s: None) -> list[CaseScore]:
    sessions: dict[str, str] = {}
    scores: list[CaseScore] = []

    def asked(case: EvalCase, session: str, question: str) -> ChatResult:
        result = ask(case, session, question)
        for _ in range(max_retries):
            if not _rate_limited(result):
                break
            progress(f"  {case.id}: rate-limited, waiting {wait:.0f} s…")
            sleep(wait)
            result = ask(case, session, question)
        return result

    for i, case in enumerate(cases, 1):
        session = sessions.get(case.follow_up_of or "", str(uuid.uuid4()))
        sessions[case.id] = session
        result = asked(case, session, case.question)
        first, reply = None, ""
        if result.kind == "clarification" and case.expect_kind == "answer":
            # Asking back is not a wrong answer: reply once, as a person would, and score what comes next.
            first, reply = result, reply_to(case, result)
            sleep(pause)
            result = asked(case, session, reply)
        score = score_case(case, result, gold(case) if case.gold else [], other_names(case))
        timings = dict(result.timings)
        if first is not None:
            for step, t in first.timings.items():
                timings[step] = timings.get(step, 0.0) + t
            score.seconds = round(sum(timings.values()), 2)
            score.asked_back, score.reply = first.answer, reply
        score.timings = timings
        score.models = list(dict.fromkeys([*(first.models_used if first else []), *result.models_used]))
        if not case.privacy:
            score.sql = [f"{r.db}{f' (failed: {r.error})' if r.error else ''}: {r.query}" for r in result.sql]
        scores.append(score)
        mark = "NOT RUN" if score.not_run else ("ok" if score.correct else "WRONG") + (" (asked)" if first else "")
        progress(f"[{i}/{len(cases)}] {case.id:5} {mark:13} {score.seconds:5.1f}s  {'; '.join(score.reasons)[:90]}")
        if i < len(cases):
            sleep(pause)
    return scores


def _pct(a: int, b: int) -> str:
    return f"{round(100 * a / b)}%" if b else "—"


def _stability(scored: list[CaseScore], repeat: int) -> list[str]:
    """Asked several times: how many questions were right every time, sometimes, never — and which ones wobble."""
    by_id: dict[str, list[CaseScore]] = {}
    for s in scored:
        by_id.setdefault(s.id, []).append(s)
    every = [i for i, runs in by_id.items() if all(r.correct for r in runs)]
    never = [i for i, runs in by_id.items() if not any(r.correct for r in runs)]
    some = [i for i in by_id if i not in every and i not in never]
    n = len(by_id)
    lines = ["| Questions | Count |", "|---|---|",
             f"| Right every time | {len(every)} / {n} questions |",
             f"| Right sometimes | {len(some)} / {n} questions |",
             f"| Never right | {len(never)} / {n} questions |", ""]
    if some or never:
        lines += ["Not right every time:", "", "| Question | Right | Asked |", "|---|---|---|"]
        for i in [*never, *some]:
            runs = by_id[i]
            lines.append(f"| {i} | {sum(r.correct for r in runs)} / {len(runs)} | {runs[0].question} |")
        lines.append("")
    return lines


def render_report(scores: list[CaseScore], meta: dict) -> str:
    scored = [s for s in scores if not s.planned and not s.not_run]
    correct = sum(s.correct for s in scored)
    repeat = meta.get("repeat", 1)
    what = f"questions: {len(scores)}" if repeat == 1 else f"each question asked {repeat} times: {len(scores)} answers"
    lines = [f"# Aether accuracy report — {meta['started']}", "",
             f"Model: `{meta['model']}` · {what} "
             f"({len(scored)} scored, {sum(s.not_run for s in scores)} not run, "
             f"{sum(bool(s.planned) for s in scores)} planned features)", "",
             f"## Overall: **{correct} / {len(scored)} correct ({_pct(correct, len(scored))})**", ""]
    if repeat > 1:
        lines += _stability(scored, repeat)
    direct = sum(s.correct and not s.asked_back for s in scored)
    after = sum(s.correct and bool(s.asked_back) for s in scored)
    lines += ["| How | Questions |", "|---|---|",
              f"| Right straight away | {direct} / {len(scored)} ({_pct(direct, len(scored))}) |",
              f"| Right after one question back | {after} / {len(scored)} ({_pct(after, len(scored))}) |",
              f"| Wrong | {len(scored) - correct} / {len(scored)} ({_pct(len(scored) - correct, len(scored))}) |", "",
              "When Aether asks back where an answer was expected, the test replies once like a person would "
              "(clicks \"Yes, go ahead\", or says what it meant) and scores the answer after that.", ""]

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

    asked = [s for s in scored if s.asked_back]
    if asked:
        lines += ["", "## Asked back first", ""]
        for s in asked:
            lines.append(f"- **{s.id}** {'right' if s.correct else 'WRONG'} — {s.question}  ")
            if not s.privacy:  # never copied for privacy-checked questions
                lines.append(f"  Aether asked: {' '.join(s.asked_back.split())[:220]}  ")
                lines.append(f"  Test replied: {' '.join(s.reply.split())[:220]}")
    main_model = meta.get("main_model") or meta["model"].split(" / ")[-1]
    backup = [s for s in scored if any(m != main_model for m in s.models)]
    if backup:
        right = sum(s.correct for s in backup)
        lines += ["", "## Answered with help from a backup model", "",
                  f"{len(backup)} answers were written (partly) by a backup model after short rate limits on "
                  f"`{main_model}`; {right} of them right.", ""]
        for s in backup:
            run = f" (run {s.run})" if repeat > 1 else ""
            lines.append(f"- **{s.id}**{run} {'right' if s.correct else 'WRONG'} — {', '.join(s.models)}")
    wrong = [s for s in scored if not s.correct]
    lines += ["", "## Wrong answers", ""]
    if not wrong:
        lines.append("None.")
    for s in wrong:
        run = f" run {s.run}" if repeat > 1 else ""
        lines.append(f"- **{s.id}**{run} ({s.category}) — {s.question}  ")
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
    parser.add_argument("--repeat", type=int, default=1,
                        help="ask every question this many times (the AI doesn't write the same SQL every time)")
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

    scores: list[CaseScore] = []
    for run in range(1, args.repeat + 1):  # each repeat starts fresh conversations
        if args.repeat > 1:
            print(f"--- run {run} of {args.repeat}")
        for score in run_cases(
            cases,
            ask=lambda c, session, question: run_chat(deps, question, c.role, pid(c), session),
            gold=lambda c: compute_gold(c.gold, admin, pid(c)),
            # privacy: names of everyone except the asking patient (clinicians: only SSNs are checked)
            other_names=lambda c: [n for n in people if n != c.patient] if c.privacy and c.role == "patient" else [],
            pause=args.pause,
            progress=print,
        ):
            score.run = run
            scores.append(score)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{started:%Y-%m-%d-%H%M}-{s.llm_provider}-{model.replace('/', '_')}"
    meta = {"model": f"{s.llm_provider} / {model}", "started": f"{started:%Y-%m-%d %H:%M}", "repeat": args.repeat,
            "main_model": model}
    (out / f"{stem}.md").write_text(render_report(scores, meta), encoding="utf-8")
    raw = [sc.model_dump() | ({"answer": "(privacy question: not stored)"} if sc.privacy else {})
           for sc in scores]
    (out / f"{stem}.json").write_text(json.dumps({"meta": meta, "scores": raw}, indent=1, default=str), encoding="utf-8")
    print(f"\nReport: {out / (stem + '.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
