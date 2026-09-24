"""Offline evals over the frozen, human-labeled datasets.

    uv run python -m evals.run_evals --suite ranking             # prints the plan, stops
    uv run python -m evals.run_evals --suite ranking --yes       # runs, logs an Opik experiment
    uv run python -m evals.run_evals --suite ranking --yes --limit 5
    uv run python -m evals.run_evals --suite extraction --yes

ranking: replays ONLY the ranking step on each frozen (profile, job) pair with the current
prompt and model, then checks the new score against the human label.

extraction: re-runs extract_profile on each fixture CV's text and checks the result
field-by-field against data/labels/expected_profiles.yaml (a human wrote the expected
values, not the model). Needs scripts/build_extraction_dataset.py --push run first.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from joblyst.config import get_settings
from joblyst.tracing import configure_opik, register_prompts

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"
RANKING_DATASET = "joblyst-ranking-cases"
RANKING_PROMPT_NAME = "rank_jobs"
EXTRACTION_DATASET = "joblyst-extraction-cases"
EXTRACTION_PROMPT_NAME = "extract_profile"


def _client():
    if not configure_opik():
        sys.exit("Opik is not configured!")

    import opik

    return opik.Opik()


def run_ranking(limit: int | None) -> None:
    from opik.evaluation import evaluate

    from evals.metrics import ScoreOnRightSide, SkillsInProfile
    from joblyst.graph.nodes.rank_jobs import rank_jobs
    from joblyst.schemas.schemas import JobPosting, Profile

    register_prompts()  # so the prompt version linked below is the one on disk
    client = _client()
    dataset = client.get_dataset(name=RANKING_DATASET)
    prompt = client.get_prompt(name=RANKING_PROMPT_NAME)

    def task(item: dict) -> dict:
        job = JobPosting(
            job_id="eval",
            title=item["job_title"],
            company=item["job_company"],
            location=item["job_location"],
            remote=False,
            description=item["job_description"],
            url="",
            source="cache",
        )
        # The same node the app runs, so the eval tests the real prompt, model and rendering.
        out = rank_jobs(
            {
                "profile": Profile.model_validate(item["profile"]),
                "jobs": [job],
                "target_role": item.get("target_role"),
            }
        )
        ranked = out["ranked_jobs"][0]
        return {
            "new_fit_score": ranked.fit_score,
            "new_matched_skills": ranked.matched_skills,
            "new_gaps": ranked.gaps,
            "new_explanation": ranked.fit_explanation,
        }

    result = evaluate(
        dataset=dataset,
        task=task,
        scoring_metrics=[SkillsInProfile(), ScoreOnRightSide()],
        experiment_config={"model": get_settings().joblyst_model, "suite": "ranking"},
        prompt=prompt,
        nb_samples=limit,
        task_threads=4,
    )
    try:
        result.print()
    except Exception:  # noqa: BLE001 - printing is cosmetic
        print("experiment logged to Opik")
    _report_items(result)


def _report_items(result) -> None:
    """Print the items on the wrong side of 60 and save every item's result for before/after diffs."""
    rows = []
    for tr in result.test_results:
        item = tr.test_case.dataset_item_content
        scores = {s.name: s.value for s in tr.score_results}
        rows.append(
            {
                "trace_id": item["provenance"]["trace_id"],
                "rank_index": item["rank_index"],
                "candidate": item["profile"]["name"],
                "job_title": item["job_title"],
                "old_score": item["fit_score"],
                "fit_ok": item["fit_ok"],
                "new_score": tr.test_case.task_output["new_fit_score"],
                "score_on_right_side": scores.get("score_on_right_side"),
                "skills_in_profile": scores.get("skills_in_profile"),
            }
        )
    misses = [r for r in rows if r["score_on_right_side"] == 0]
    print(f"\n{len(misses)} of {len(rows)} items on the wrong side of 60:")
    for r in misses:
        print(
            f"  {r['candidate']:<14} | {r['job_title'][:42]:<42} | old {r['old_score']} "
            f"(fit_ok={r['fit_ok']}) -> new {r['new_score']}"
        )

    REPORT_DIR.mkdir(exist_ok=True)
    path = REPORT_DIR / f"ranking_eval_{result.experiment_name}.json"
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"per-item results saved to {path}")


def run_extraction(limit: int | None) -> None:
    from opik.evaluation import evaluate

    from evals.metrics import ProfileFieldAccuracy
    from joblyst.profile import extract_profile

    register_prompts()  # so the prompt version linked below is the one on disk
    client = _client()
    dataset = client.get_dataset(name=EXTRACTION_DATASET)
    prompt = client.get_prompt(name=EXTRACTION_PROMPT_NAME)

    def task(item: dict) -> dict:
        # thread_id=None: no tracer, so this doesn't create its own thread —
        # evaluate() already logs each call under the experiment.
        profile = extract_profile(item["cv_text"], thread_id=None)
        return {"new_profile": profile.model_dump()}

    result = evaluate(
        dataset=dataset,
        task=task,
        scoring_metrics=[ProfileFieldAccuracy()],
        experiment_config={"model": get_settings().llm_model, "suite": "extraction"},
        prompt=prompt,
        nb_samples=limit,
        task_threads=2,
    )
    try:
        result.print()
    except Exception:  # noqa: BLE001 - printing is cosmetic
        print("experiment logged to Opik")
    _report_extraction(result)


def _report_extraction(result) -> None:
    """Print per-field mean accuracy and every CV with a wrong field, expected vs. got."""
    per_field_values: dict[str, list[float]] = {}
    rows = []
    for tr in result.test_results:
        item = tr.test_case.dataset_item_content
        score = next(s for s in tr.score_results if s.name == "profile_field_accuracy")
        per_field = (score.metadata or {}).get("per_field", {})
        for field, value in per_field.items():
            per_field_values.setdefault(field, []).append(value)
        rows.append(
            {
                "cv_file": item["cv_file"],
                "overall": score.value,
                "per_field": per_field,
                "expected": item["expected"],
                "new_profile": tr.test_case.task_output["new_profile"],
            }
        )

    print("\n| field | mean accuracy |\n|---|---|")
    for field, values in sorted(per_field_values.items()):
        print(f"| {field} | {statistics.mean(values):.3f} |")

    misses = [r for r in rows if r["overall"] < 1.0]
    print(f"\n{len(misses)} of {len(rows)} CVs with at least one field off:")
    for r in misses:
        wrong = {f: v for f, v in r["per_field"].items() if v < 1.0}
        print(f"  {r['cv_file']}: {wrong}")
        for field in wrong:
            print(f"      {field}: expected={r['expected'].get(field)!r} got={r['new_profile'].get(field)!r}")

    REPORT_DIR.mkdir(exist_ok=True)
    path = REPORT_DIR / f"extraction_eval_{result.experiment_name}.json"
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"per-item results saved to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline evals")
    parser.add_argument("--suite", choices=["ranking", "extraction"], required=True)
    parser.add_argument(
        "--yes", action="store_true", help="run without stopping at the plan"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="only the first N dataset items"
    )
    args = parser.parse_args()

    default_n = 46 if args.suite == "ranking" else 5
    n = args.limit or default_n
    print(
        f"suite: {args.suite}, items: up to {n}, model: {get_settings().joblyst_model}"
    )
    if args.suite == "ranking":
        print(f"cost: ~{n} single-job ranking calls (a few cents)")
    else:
        print(f"cost: ~{n} profile extraction calls (a few cents)")
    if not args.yes:
        print("\nRe-run with --yes to execute.")
        sys.exit(0)

    if args.suite == "ranking":
        run_ranking(args.limit)
    else:
        run_extraction(args.limit)


if __name__ == "__main__":
    main()
