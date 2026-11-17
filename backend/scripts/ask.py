"""Ask Aether a question from the terminal and see everything that happened.

Run from backend/:
    python -m scripts.ask "How many patients are in the system?"
    python -m scripts.ask "What medications am I taking?" --role patient --patient-id <id>
    python -m scripts.ask --list-patients
"""

import argparse
import uuid

from app.config import get_settings
from app.db.patients import list_patients
from app.graph.runner import build_deps, run_chat


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask Aether a question.")
    parser.add_argument("question", nargs="?")
    parser.add_argument("--role", choices=["clinician", "patient"], default="clinician")
    parser.add_argument("--patient-id")
    parser.add_argument("--list-patients", action="store_true", help="print patient ids and names, then exit")
    args = parser.parse_args()

    deps = build_deps(get_settings())
    if args.list_patients:
        for p in list_patients(deps.engines["clinical"]):
            print(f"{p['id']}  {p['name']}  ({p['gender']}, born {p['birthdate']})")
        return
    if not args.question:
        parser.error("a question is required")

    result = run_chat(deps, args.question, args.role, args.patient_id, str(uuid.uuid4()))
    print(f"\n[{result.kind}] {result.answer}\n")
    for i, attempt in enumerate(result.sql, 1):
        status = f"FAILED: {attempt.error}" if attempt.error else "ok"
        print(f"SQL attempt {i} on {attempt.db} ({status}):\n  {attempt.query}\n")
    if result.table:
        print(f"Rows: {result.table.total_rows}{' (truncated)' if result.table.truncated else ''}")
    if result.sources:
        print("Sources:", ", ".join(result.sources))
    if result.unverified_numbers:
        print("Unverified numbers:", ", ".join(result.unverified_numbers))
    total = sum(result.timings.values())
    print("Timings: " + ", ".join(f"{k} {v:.2f}s" for k, v in result.timings.items()) + f"  | total {total:.2f}s")


if __name__ == "__main__":
    main()
