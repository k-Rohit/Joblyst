"""Build the extraction-cases dataset from the hand-verified expected profiles.

    uv run python scripts/build_extraction_dataset.py           # dry run: print items
    uv run python scripts/build_extraction_dataset.py --push    # push to Opik

Source: data/labels/expected_profiles.yaml (verified: true entries only) + the
fixture CV text. No traces involved — unlike the ranking dataset, this one is
built straight from ground truth a human wrote, not sampled from a batch run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from joblyst.tools.cv_reader import extract_cv_content
from joblyst.tracing import configure_opik

EXTRACTION_DATASET = "joblyst-extraction-cases"
LABELS_PATH = Path(__file__).parent.parent / "data" / "labels" / "expected_profiles.yaml"
CV_DIR = Path(__file__).parent.parent / "data" / "fixture_cvs"


def _client():
    if not configure_opik():
        sys.exit("Opik is not configured!")

    import opik

    return opik.Opik()


def build_items() -> list[dict]:
    entries = yaml.safe_load(LABELS_PATH.read_text())
    items = []
    for entry in entries:
        if not entry.get("verified"):
            continue
        items.append(
            {
                "cv_file": entry["cv_file"],
                "cv_text": extract_cv_content(CV_DIR / entry["cv_file"]),
                "expected": entry["expected"],
            }
        )
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the extraction eval dataset")
    parser.add_argument("--push", action="store_true", help="push to Opik (default: dry run, print only)")
    args = parser.parse_args()

    items = build_items()
    print(f"built {len(items)} extraction items (verified entries in {LABELS_PATH.name})")
    if not items:
        sys.exit("No verified entries in expected_profiles.yaml.")

    if not args.push:
        print("dry run; first item:")
        print(json.dumps(items[0], indent=2, ensure_ascii=False)[:2000])
        return

    client = _client()
    dataset = client.get_or_create_dataset(
        EXTRACTION_DATASET, description="Hand-verified profile extraction cases (Phase 4)."
    )
    dataset.insert(items)  # Opik dedupes identical items — safe to re-run
    print(f"Pushed {len(items)} items to Opik dataset '{EXTRACTION_DATASET}'.")


if __name__ == "__main__":
    main()
