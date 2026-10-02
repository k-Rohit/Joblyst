"""Tailoring batch: does the CV rewriter make things up, and does the validator catch it?

For each case: run the real job search on a fresh thread, pick one of the ranked
jobs, then tailor for it ON THE SAME THREAD. Both invocations have to happen in
the same process — ``run_tailor`` reads the profile, cv_text and ranked_jobs back
out of the thread's MemorySaver checkpoint, which only lives in memory.

Writes reports/tailor_batch.json, whose summary carries the first fabrication-rate
numbers this project has ever produced, split by validator stage (the free difflib
pass vs the LLM drift judge).

Tags every tailoring trace ``tailor-batch``, which is what
scripts/build_eval_dataset.py --kind tailoring reads.

Usage:
    uv run python scripts/run_tailor_batch.py                  # prints projected cost, stops
    uv run python scripts/run_tailor_batch.py --yes             # actually runs
    uv run python scripts/run_tailor_batch.py --yes --limit 2   # try 2 cases first
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import Counter
from pathlib import Path
from uuid import uuid4

from joblyst.profile import extract_profile
from joblyst.runner import run_search, run_tailor
from joblyst.schemas.schemas import Profile
from joblyst.tools.cv_reader import extract_cv_content
from joblyst.tracing import register_prompts

_CV_DIR = Path(__file__).parent.parent / "data" / "fixture_cvs"
REPORT_PATH = Path(__file__).parent.parent / "reports" / "tailor_batch.json"
_PROFILE_CACHE_PATH = Path(__file__).parent.parent / "data" / "fixture_profiles_cache.json"

# One search (~$0.01) plus one tailor call (~$0.005) per case.
COST_PER_CASE_ESTIMATE = 0.015

SEARCH_TAGS = ["tailor-batch-search"]  # NOT "baseline-batch" — that would pollute the ranking dataset
TAILOR_TAGS = ["tailor-batch"]  # what build_eval_dataset.py --kind tailoring filters on

# pick: 0 = best-ranked job, -1 = worst-ranked, None = a job id that doesn't exist.
#
# The worst-ranked pick is the fabrication stress test: tailoring for a job the
# candidate barely fits is exactly where a model is tempted to invent skills.
# locations/remote_ok stand in for the user's own preference inputs (see run_batch.py).
CASES: list[dict] = [
    {"case_id": "junior_ds_in|top", "cv": "junior_ds_in.pdf", "pick": 0,
     "target_role": None, "locations": ["Bengaluru, India"], "remote_ok": False},
    {"case_id": "junior_ds_in|worst", "cv": "junior_ds_in.pdf", "pick": -1,
     "target_role": None, "locations": ["Bengaluru, India"], "remote_ok": False},
    {"case_id": "senior_mle_in|top", "cv": "senior_mle_in.pdf", "pick": 0,
     "target_role": None, "locations": ["Hyderabad, India"], "remote_ok": False},
    {"case_id": "senior_mle_in|worst", "cv": "senior_mle_in.pdf", "pick": -1,
     "target_role": None, "locations": ["Hyderabad, India"], "remote_ok": False},
    {"case_id": "career_changer_in|top", "cv": "career_changer_in.pdf", "pick": 0,
     "target_role": None, "locations": ["Bengaluru, India"], "remote_ok": True},
    {"case_id": "career_changer_in|worst", "cv": "career_changer_in.pdf", "pick": -1,
     "target_role": None, "locations": ["Bengaluru, India"], "remote_ok": True},
    {"case_id": "lead_in_remote|top", "cv": "lead_in_remote.pdf", "pick": 0,
     "target_role": None, "locations": ["Pune, India"], "remote_ok": True},
    {"case_id": "lead_in_remote|worst", "cv": "lead_in_remote.pdf", "pick": -1,
     "target_role": None, "locations": ["Pune, India"], "remote_ok": True},
    {"case_id": "mid_analyst_in|top", "cv": "mid_analyst_in.pdf", "pick": 0,
     "target_role": None, "locations": ["Gurugram, India"], "remote_ok": False},
    {"case_id": "mid_analyst_in|worst", "cv": "mid_analyst_in.pdf", "pick": -1,
     "target_role": None, "locations": ["Gurugram, India"], "remote_ok": False},
    {"case_id": "data_engineer|top", "cv": "data_engineer.pdf", "pick": 0,
     "target_role": None, "locations": ["Pune, Maharashtra"], "remote_ok": False},
    {"case_id": "data_engineer|worst", "cv": "data_engineer.pdf", "pick": -1,
     "target_role": None, "locations": ["Pune, Maharashtra"], "remote_ok": False},
    # The pivot case: tailoring for a role the candidate has projects for but no job history.
    {"case_id": "data_engineer|ai_pivot_top", "cv": "data_engineer.pdf", "pick": 0,
     "target_role": "AI Engineer", "locations": ["Pune, Maharashtra"], "remote_ok": False},
    # Deliberate failure: an unknown job id must degrade gracefully, not crash.
    {"case_id": "junior_ds_in|unknown_job", "cv": "junior_ds_in.pdf", "pick": None,
     "target_role": None, "locations": ["Bengaluru, India"], "remote_ok": False},
]


def _load_cvs_and_profiles(cv_dir: Path, cache_path: Path) -> tuple[dict[str, str], dict[str, Profile]]:
    """Read each fixture CV's text (free) and profile (an LLM call, cached to disk)."""
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
        profile = extract_profile(cv_texts[cv], thread_id=f"tailor-extract-{cv}", tags=SEARCH_TAGS)
        profiles[cv] = profile
        cached_raw[cv] = profile.model_dump()
        dirty = True

    if dirty:
        cache_path.write_text(json.dumps(cached_raw, indent=2, ensure_ascii=False))
    return cv_texts, profiles


def _run_case(case: dict, profile: Profile, cv_text: str) -> dict:
    """Search, pick a job, tailor for it — all on one thread, then shape a report row."""
    thread_id = str(uuid4())  # fresh per case: a reused thread would reuse its checkpoint
    # Stand in for the user's own preference inputs.
    profile = profile.model_copy(update={"locations": case["locations"], "remote_ok": case["remote_ok"]})

    search = run_search(
        profile, cv_text, thread_id=thread_id, tags=SEARCH_TAGS, target_role=case["target_role"]
    )
    row = {
        "case_id": case["case_id"],
        "cv_file": case["cv"],
        "thread_id": thread_id,
        "target_role": case["target_role"],
        "n_jobs_ranked": len(search.ranked_jobs),
        "search_errors": search.errors,
    }
    if not search.ranked_jobs:
        return {**row, "tailored": False, "skip_reason": "search returned no ranked jobs"}

    if case["pick"] is None:
        job_id, job_title, fit_score = "no-such-job-id", None, None
    else:
        picked = search.ranked_jobs[case["pick"]]
        job_id, job_title, fit_score = picked.job.job_id, picked.job.title, picked.fit_score

    result = run_tailor(thread_id=thread_id, selected_job_id=job_id, tags=TAILOR_TAGS)
    report = result.fabrication_report
    pack = result.pack
    return {
        **row,
        "selected_job_id": job_id,
        "job_title": job_title,
        "fit_score": fit_score,
        "tailored": pack is not None,
        "tailor_errors": result.errors,
        # The fabrication numbers — the point of this batch.
        "fabrication_flags": result.fabrication_flags,
        "claims_checked": report.claims_checked if report else 0,
        "flagged": [f.model_dump() for f in report.flagged] if report else [],
        # Prompt contracts the TailoringPack docstring states but nothing measures yet.
        "cover_letter_words": len(pack.cover_letter.split()) if pack else 0,
        "n_bullets": sum(len(e.bullets) for e in pack.cv.experience) if pack else 0,
        "honesty_note_words": len(pack.honesty_note.split()) if pack else 0,
    }


def _failed_case(case: dict, exc: Exception) -> dict:
    """A case that raised — recorded, not silently dropped, so the batch keeps going."""
    return {
        "case_id": case["case_id"],
        "cv_file": case["cv"],
        "tailored": False,
        "crashed": True,
        "error_message": f"{type(exc).__name__}: {exc}",
        "fabrication_flags": 0,
        "claims_checked": 0,
        "flagged": [],
    }


def _summarize(rows: list[dict]) -> dict:
    tailored = [r for r in rows if r.get("tailored")]
    flags = sum(r.get("fabrication_flags", 0) for r in rows)
    claims = sum(r.get("claims_checked", 0) for r in rows)
    # Split by stage: the deterministic difflib pass and the LLM drift judge are
    # two different kinds of claim, and a single rate would hide which one fired.
    by_stage = Counter(f.get("stage", "unknown") for r in rows for f in r.get("flagged", []))
    letters = [r["cover_letter_words"] for r in tailored if r.get("cover_letter_words")]
    return {
        "cases": len(rows),
        "tailored": len(tailored),
        "crashed": sum(1 for r in rows if r.get("crashed")),
        "graceful_failures": sum(1 for r in rows if not r.get("tailored") and not r.get("crashed")),
        "total_claims_checked": claims,
        "total_fabrication_flags": flags,
        "fabrication_rate": round(flags / claims, 4) if claims else 0.0,
        "flags_by_stage": dict(by_stage),
        "runs_with_any_flag": sum(1 for r in rows if r.get("fabrication_flags", 0) > 0),
        "cover_letter_words_mean": round(statistics.mean(letters), 1) if letters else 0,
        "cover_letters_over_350": sum(1 for w in letters if w > 350),
    }


def _checkpoint(rows: list[dict]) -> None:
    """Write the report after every case so a crash mid-batch doesn't lose earlier work."""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps({"summary": _summarize(rows), "runs": rows}, indent=2, ensure_ascii=False))


def run(cases: list[dict], cv_texts: dict[str, str], profiles: dict[str, Profile]) -> dict:
    rows: list[dict] = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['case_id']}...", flush=True)
        try:
            row = _run_case(case, profiles[case["cv"]], cv_texts[case["cv"]])
            if row.get("tailored"):
                print(f"  {row['fabrication_flags']} flag(s) / {row['claims_checked']} claims checked")
            else:
                print(f"  not tailored: {row.get('skip_reason') or row.get('tailor_errors')}")
        except Exception as exc:  # noqa: BLE001 - one bad case must not kill the batch
            row = _failed_case(case, exc)
            print(f"  CRASHED: {row['error_message']}")
        rows.append(row)
        _checkpoint(rows)
    return {"summary": _summarize(rows), "runs": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Tailoring batch + first fabrication numbers")
    parser.add_argument("--yes", action="store_true", help="run without the cost confirmation prompt")
    parser.add_argument("--limit", type=int, default=None, help="cap the number of cases (default: all)")
    args = parser.parse_args()

    cases = CASES[: args.limit] if args.limit else CASES
    print(f"Planned cases: {len(cases)} (one search + one tailor each)")
    print(f"Projected cost: ~${len(cases) * COST_PER_CASE_ESTIMATE:.2f}")
    if not args.yes:
        print("\nRe-run with --yes to execute.")
        sys.exit(0)

    register_prompts()  # so these traces sit against the current prompt versions
    cv_texts, profiles = _load_cvs_and_profiles(_CV_DIR, _PROFILE_CACHE_PATH)
    report = run(cases, cv_texts, profiles)

    print(f"\nWrote {REPORT_PATH}")
    print("Summary:")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
