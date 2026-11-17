"""Build the drug-label library (run once; re-runs are quick thanks to the cache).

Plain English:
  1. Ask clinical_db which medicines appear in our patient records (about 150).
  2. For each, fetch its official FDA label from openFDA (free; we wait a moment between
     requests to be polite). Labels are saved in backend/data/drug_labels/ so we never
     download the same one twice.
  3. Keep the useful sections, cut them into passages, turn each passage into numbers with
     a small local AI model (downloaded once, ~80 MB) and store them in backend/chroma/.

Run from backend/:   python -m scripts.build_drug_index           (add what's new)
                     python -m scripts.build_drug_index --reset   (rebuild from scratch)
"""

import argparse
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

from app.config import get_settings
from app.rag.openfda import fetch_label, label_sections
from app.rag.store import DrugLabelStore


def build_index(medications: list[tuple[str, str]], client: httpx.Client, cache_dir: Path,
                store: DrugLabelStore, pause: float = 0.3) -> dict:
    missing, with_label, chunks = [], 0, 0
    for i, (code, description) in enumerate(medications, 1):
        cached = (cache_dir / f"{code}.json").exists()
        label = fetch_label(client, code, description, cache_dir)
        if label is None:
            missing.append(description)
        else:
            with_label += 1
            chunks += store.add(label_sections(label, code, description))
        if not cached and pause:
            time.sleep(pause)
        if i % 25 == 0:
            print(f"  {i}/{len(medications)} medicines processed")
    return {"medications": len(medications), "with_label": with_label, "missing": missing, "chunks": chunks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete the library and rebuild it")
    args = parser.parse_args(argv)
    s = get_settings()

    engine = create_engine(s.clinical_url(admin=True))
    with engine.connect() as conn:
        meds = [(str(code), desc) for code, desc in conn.execute(
            text("SELECT DISTINCT code, description FROM medications ORDER BY description"))]
    engine.dispose()
    print(f"{len(meds)} distinct medicines in the patient records")

    store = DrugLabelStore.create(s.chroma_dir, reset=args.reset)
    with httpx.Client(headers={"User-Agent": "aether-learning-project"}) as client:
        summary = build_index(meds, client, s.data_dir / "drug_labels", store)
    print(f"Labels found: {summary['with_label']}/{summary['medications']}; passages stored: {store.count()}")
    if summary["missing"]:
        print("No FDA label found for:")
        for desc in summary["missing"]:
            print(f"  - {desc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
