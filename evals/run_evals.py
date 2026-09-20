"""Offline evals over the frozen, human-labeled datasets.

    uv run python -m evals.run_evals --suite ranking            # prints the plan, stops
    uv run python -m evals.run_evals --suite ranking --yes      # runs, logs an Opik experiment
    uv run python -m evals.run_evals --suite ranking --yes --limit 5

ranking: replays ONLY the ranking step on each frozen (profile, job) pair with the current
prompt and model, then checks the new score against the human label.
"""

from __future__ import annotations

import argparse
import sys

from joblyst.config import get_settings
from joblyst.tracing import configure_opik, register_prompts

RANKING_DATASET = "joblyst-ranking-cases"
RANKING_PROMPT_NAME = "rank_jobs"


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
            {"profile": Profile.model_validate(item["profile"]), "jobs": [job]}
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline evals")
    parser.add_argument("--suite", choices=["ranking"], required=True)
    parser.add_argument(
        "--yes", action="store_true", help="run without stopping at the plan"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="only the first N dataset items"
    )
    args = parser.parse_args()

    n = args.limit or 46
    print(
        f"suite: {args.suite}, items: up to {n}, model: {get_settings().joblyst_model}"
    )
    print(f"cost: ~{n} single-job ranking calls (a few cents)")
    if not args.yes:
        print("\nRe-run with --yes to execute.")
        sys.exit(0)

    run_ranking(args.limit)


if __name__ == "__main__":
    main()
