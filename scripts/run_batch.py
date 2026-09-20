"""Phase 2 baseline batch runner.

Runs the real search graph over the 6 fixture CVs (5 synthetic personas plus
the real resume) across a small committed case matrix, tags every trace
``baseline-batch``, and writes
reports/baseline.json. This is the raw material every later eval phase reads
from (Phase 3 samples best/middle/worst job per trace from these exact traces).

This does NOT fix anything it surfaces — a bad score or a search failure gets
recorded, not patched. Fixes happen later, informed by what this finds.

Usage:
    uv run python scripts/run_batch.py            # prints projected cost, then stops
    uv run python scripts/run_batch.py --yes       # actually runs
    uv run python scripts/run_batch.py --yes --limit 2   # test with 2 cases first
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path
from uuid import uuid4

from joblyst.profile import extract_profile
from joblyst.runner import run_search
from joblyst.schemas.schemas import Profile
from joblyst.tools.cv_reader import extract_cv_content
from joblyst.tracing import register_prompts

_CV_DIR = Path(__file__).parent.parent / "data" / "fixture_cvs"
REPORT_PATH = Path(__file__).parent.parent / "reports" / "baseline.json"

# Dev cache only, not the golden dataset — regenerate anytime by deleting this
# file (e.g. after changing EXTRACT_PROFILE_PROMPT, since a stale cache would
# silently hide the effect of a prompt change).
_PROFILE_CACHE_PATH = Path(__file__).parent.parent / "data" / "fixture_profiles_cache.json"

# Rough per-run cost with gpt-4o-mini ranking ~20 jobs (batched) plus an
# occasional reformulation loop. A guess, not a measurement — tighten it once
# Opik shows real per-run cost for this project.
COST_PER_RUN_ESTIMATE = 0.01

# 6 plain runs (one per CV, including the real resume) plus one deliberately
# hard case: the real resume pivoting toward AI engineering roles.
CASES: list[dict] = [
    {"case_id": "junior_ds_in|plain", "cv": "junior_ds_in.pdf", "target_role": None},
    {"case_id": "senior_mle_in|plain", "cv": "senior_mle_in.pdf", "target_role": None},
    {"case_id": "career_changer_in|plain", "cv": "career_changer_in.pdf", "target_role": None},
    {"case_id": "lead_in_remote|plain", "cv": "lead_in_remote.pdf", "target_role": None},
    {"case_id": "mid_analyst_in|plain", "cv": "mid_analyst_in.pdf", "target_role": None},
    {"case_id": "data_engineer|plain", "cv": "data_engineer.pdf", "target_role": None},
    {"case_id": "data_engineer|ai_engineer_pivot", "cv": "data_engineer.pdf", "target_role": "AI Engineer"},
]


def _load_cvs_and_profiles(cv_dir: Path, cache_path: Path) -> tuple[dict[str, str], dict[str, Profile]]:
    """Read every fixture CV's text (free) and profile (an LLM call, cached to disk).

    cv_text is re-extracted every run — pypdf parsing is free and deterministic,
    so there's nothing worth caching there. extract_profile is a real LLM call,
    so it's cached to cache_path and only re-run for a CV that isn't in it yet.
    """
    cached_raw: dict[str, dict] = {}
    if cache_path.exists():
        cached_raw = json.loads(cache_path.read_text())

    cv_texts: dict[str, str] = {}
    profiles: dict[str, Profile] = {}
    dirty = False
    for cv in sorted(os.listdir(cv_dir)):
        if not cv.endswith(".pdf"):
            continue
        cv_texts[cv] = extract_cv_content(cv_dir / cv)
        if cv in cached_raw:
            profiles[cv] = Profile.model_validate(cached_raw[cv])
            continue
        profile = extract_profile(cv_texts[cv], thread_id=f"baseline-extract-{cv}", tags=["baseline-batch"])
        profiles[cv] = profile
        cached_raw[cv] = profile.model_dump()
        dirty = True

    if dirty:
        cache_path.write_text(json.dumps(cached_raw, indent=2, ensure_ascii=False))
    return cv_texts, profiles


def _run_case(case: dict, profile: Profile, cv_text: str) -> dict:
    """Run one case through the real search graph and shape it into a report row."""
    result = run_search(
        profile,
        cv_text,
        thread_id=str(uuid4()),  # fresh per case — never reuse, or checkpoints bleed together
        tags=["baseline-batch"],
        target_role=case["target_role"],
    )
    return {
        "case_id": case["case_id"],
        "cv_file": case["cv"],
        "target_role": case["target_role"],
        "failed": False,
        "error_message": None,
        "n_jobs_ranked": len(result.ranked_jobs),
        "reformulation_count": result.reformulation_count,
        "jobs_sources": result.jobs_sources,
        "fit_scores": [r.fit_score for r in result.ranked_jobs],
        "errors": result.errors,
    }


def _failed_case(case: dict, exc: Exception) -> dict:
    """A case that raised — recorded, not silently dropped, so the batch keeps going."""
    return {
        "case_id": case["case_id"],
        "cv_file": case["cv"],
        "target_role": case["target_role"],
        "failed": True,
        "error_message": f"{type(exc).__name__}: {exc}",
        "n_jobs_ranked": 0,
        "reformulation_count": 0,
        "jobs_sources": [],
        "fit_scores": [],
        "errors": [],
    }


def _summarize(rows: list[dict]) -> dict:
    all_scores = [s for r in rows for s in r["fit_scores"]]
    return {
        "runs": len(rows),
        "failures": sum(1 for r in rows if r["failed"]),
        "empty_result_runs": sum(1 for r in rows if not r["failed"] and r["n_jobs_ranked"] == 0),
        "reformulation_triggered": sum(1 for r in rows if r["reformulation_count"] > 0),
        "fit_score_mean": round(statistics.mean(all_scores), 1) if all_scores else 0,
        "fit_score_min": min(all_scores) if all_scores else None,
        "fit_score_max": max(all_scores) if all_scores else None,
    }


def _checkpoint(rows: list[dict]) -> None:
    """Write the report after every run so a crash mid-batch doesn't lose earlier results."""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps({"summary": _summarize(rows), "runs": rows}, indent=2, ensure_ascii=False))


def run(cases: list[dict], cv_texts: dict[str, str], profiles: dict[str, Profile]) -> dict:
    rows: list[dict] = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['case_id']}...", flush=True)
        try:
            row = _run_case(case, profiles[case["cv"]], cv_texts[case["cv"]])
        except Exception as exc:  # noqa: BLE001 - one bad case must not kill the sweep
            row = _failed_case(case, exc)
            print(f"  FAILED: {row['error_message']}")
        rows.append(row)
        _checkpoint(rows)  # crash-safe: report reflects every completed case
    return {"summary": _summarize(rows), "runs": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 baseline batch runner")
    parser.add_argument("--yes", action="store_true", help="run without the cost confirmation prompt")
    parser.add_argument("--limit", type=int, default=None, help="cap the number of cases (default: all)")
    args = parser.parse_args()

    cases = CASES[: args.limit] if args.limit else CASES
    projected = len(cases) * COST_PER_RUN_ESTIMATE
    print(f"Planned runs: {len(cases)}")
    print(f"Projected cost: ~${projected:.2f} (at ~${COST_PER_RUN_ESTIMATE:.3f}/run)")

    if not args.yes:
        print("\nRe-run with --yes to execute.")
        sys.exit(0)

    register_prompts()  # so this batch's traces sit against the current prompt versions
    cv_texts, profiles = _load_cvs_and_profiles(_CV_DIR, _PROFILE_CACHE_PATH)
    report = run(cases, cv_texts, profiles)

    print(f"\nWrote {REPORT_PATH}")
    print("Summary:")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
