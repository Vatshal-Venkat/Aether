"""Empty the saved queries (or forget one question), so Aether writes that SQL afresh next time.

Usage:
  python -m scripts.forget_saved_queries                                   # forget all
  python -m scripts.forget_saved_queries --role clinician --question "How many patients have diabetes?"
"""

import argparse

from app.config import get_settings
from app.memory.saved_queries import SavedQueryStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--role", choices=["clinician", "patient"])
    parser.add_argument("--question")
    args = parser.parse_args()
    if bool(args.role) != bool(args.question):
        parser.error("give both --role and --question, or neither (forget all)")
    store = SavedQueryStore(get_settings().saved_queries_path, version="")
    removed = store.forget(args.role, args.question)
    print(f"Forgot {removed} saved quer{'y' if removed == 1 else 'ies'}.")


if __name__ == "__main__":
    main()
