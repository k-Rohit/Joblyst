"""Build the ranking-cases / tailoring-cases datasets from baseline-batch traces.

    uv run python scripts/build_eval_dataset.py --kind ranking            # dry run: print items
    uv run python scripts/build_eval_dataset.py --kind ranking --push     # push to Opik
    uv run python scripts/build_eval_dataset.py --kind tailoring --push

ranking-cases:   one item per ranked job: best, worst, and up to 5 jobs scoring >= 60
                 per trace (where wrong scores hurt), from baseline-batch traces (built by scripts/run_batch.py).
tailoring-cases: one item per tailoring run, from tailor-batch traces (not
                 built yet — scripts/run_tailor_batch.py doesn't exist).

Needs OPIK_API_KEY; makes no LLM calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from typing import Any

from joblyst.config import get_settings
from joblyst.tracing import configure_opik

RANKING_DATASET = "joblyst-ranking-cases"
TAILORING_DATASET = "joblyst-tailoring-cases"
RANKING_TAG = "baseline-batch"
TAILORING_TAG = "tailor-batch"
MAX_RANKING_ITEMS = 40  # cap on NEW items per build
GOOD_FIT_THRESHOLD = 60  # same bar the search loop uses for a good match
GOOD_FIT_PER_TRACE = 5
MAX_TAILORING_ITEMS = 30


def _client():
    # check if opik has been configured -
    if not configure_opik():
        sys.exit("Opik is not configured!")

    import opik

    return opik.Opik()


def _get_opik_project_name() -> str:
    settings = get_settings()
    return settings.opik_project_name


def _find_spans(client, trace_id: str, name: str) -> list:
    spans = client.search_spans(
        project_name=_get_opik_project_name(), trace_id=trace_id, truncate=False
    )
    return [s for s in spans if getattr(s, "name", "") == name]


def _add_metadata(trace, span_id: str | None, tag: str) -> dict:
    return {
        "trace_id": str(trace.id),
        "thread_id": getattr(trace, "thread_id", None),
        "span_id": span_id,
        "source_tag": tag,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _existing_ranking_pairs(client) -> set[tuple[str, int]]:
    """(trace_id, rank_index) of every item already in the ranking dataset.

    Labeled items gained extra fields, so Opik no longer sees a rebuilt copy as
    a duplicate — this is what stops a re-pushed job from being labeled twice.
    """
    try:
        items = client.get_dataset(name=RANKING_DATASET).get_items()
    except Exception:  # noqa: BLE001 - dataset not created yet
        return set()
    return {(i["provenance"]["trace_id"], i["rank_index"]) for i in items}


def build_ranking_items(
    client, max_items: int, skip: set[tuple[str, int]] | None = None
) -> list[dict]:
    """One item per ranked job, sampled from the traces' final state.

    The trace OUTPUT carries the final graph state (profile + the full sorted
    ``ranked_jobs``). Per trace we take the best and worst job, plus up to
    GOOD_FIT_PER_TRACE jobs scoring >= GOOD_FIT_THRESHOLD: a low score is
    almost always right, so the model's mistakes are in the high scores.
    Pairs in ``skip`` (already in the dataset) are not built again.
    """
    skip = skip or set()
    project = _get_opik_project_name()
    traces = client.search_traces(
        project_name=project,
        filter_string=f'tags contains "{RANKING_TAG}"',
        truncate=False,
    )
    print(f"found {len(traces)} '{RANKING_TAG}' traces")

    items: list[dict] = []
    for trace in traces:
        state = _as_dict(getattr(trace, "output", None))
        profile = _as_dict(state.get("profile"))
        ranked = [_as_dict(r) for r in state.get("ranked_jobs") or []]
        if not profile or not ranked:
            continue

        ranked.sort(key=lambda r: r.get("fit_score", 0), reverse=True)
        good = [
            i
            for i, r in enumerate(ranked)
            if r.get("fit_score", 0) >= GOOD_FIT_THRESHOLD
        ]
        picks = sorted({0, len(ranked) - 1, *good[:GOOD_FIT_PER_TRACE]})
        for index in picks:
            if (str(trace.id), index) in skip:
                continue
            entry = ranked[index]
            job = _as_dict(entry.get("job"))
            if not job:
                continue
            items.append(
                {
                    "profile": profile,
                    "job_title": job.get("title", ""),
                    "job_company": job.get("company", ""),
                    "job_location": job.get("location", ""),
                    "job_description": job.get("description", ""),
                    "fit_score": entry.get("fit_score"),
                    "fit_explanation": entry.get("fit_explanation", ""),
                    "matched_skills": entry.get("matched_skills", []),
                    "gaps": entry.get("gaps", []),
                    "rank_index": index,
                    "provenance": _add_metadata(trace, None, RANKING_TAG),
                }
            )
            if len(items) >= max_items:
                return items
    return items


def build_tailoring_items(client, max_items: int) -> list[dict]:
    """One item per tailoring run: the checkpointed inputs + the generated pack."""
    project = _get_opik_project_name()
    traces = client.search_traces(
        project_name=project,
        filter_string=f'tags contains "{TAILORING_TAG}"',
        truncate=False,
    )
    print(f"found {len(traces)} '{TAILORING_TAG}' traces")

    items: list[dict] = []
    for trace in traces:
        for span in _find_spans(client, str(trace.id), "tailor"):
            # A LangGraph node span's input is the full checkpointed state, so
            # the search-invocation fields (cv_text, ranked_jobs) are available
            # even though the tailor invocation only passed selected_job_id.
            state = _as_dict(getattr(span, "input", None))
            pack = _as_dict(getattr(span, "output", None)).get("tailoring")
            cv_text = state.get("cv_text", "")
            job_id = state.get("selected_job_id")
            ranked = [_as_dict(r) for r in state.get("ranked_jobs") or []]
            job = next(
                (
                    _as_dict(r.get("job"))
                    for r in ranked
                    if _as_dict(r.get("job")).get("job_id") == job_id
                ),
                {},
            )
            if not cv_text or pack is None:
                continue
            items.append(
                {
                    "cv_text": cv_text,
                    "profile": _as_dict(state.get("profile")),
                    "selected_job_id": job_id,
                    "job_title": job.get("title", ""),
                    "job_company": job.get("company", ""),
                    "job_description": job.get("description", ""),
                    "pack": _as_dict(pack),
                    "provenance": _add_metadata(trace, str(span.id), TAILORING_TAG),
                }
            )
            if len(items) >= max_items:
                return items
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Build eval datasets from Opik traces")
    parser.add_argument("--kind", choices=["ranking", "tailoring"], required=True)
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="max new items (defaults: 40 ranking / 20 tailoring)",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="push to Opik (default: dry run, print only)",
    )
    args = parser.parse_args()

    client = _client()
    if args.kind == "ranking":
        skip = _existing_ranking_pairs(client)
        print(f"{len(skip)} ranking items already in the dataset (will be skipped)")
        items = build_ranking_items(client, args.max or MAX_RANKING_ITEMS, skip)
        dataset_name, description = (
            RANKING_DATASET,
            "Ranked-job cases exported from baseline-batch traces (Phase 3).",
        )
    else:
        items = build_tailoring_items(client, args.max or MAX_TAILORING_ITEMS)
        dataset_name, description = (
            TAILORING_DATASET,
            "Tailoring cases exported from tailor-batch traces (Phase 3).",
        )

    print(f"built {len(items)} {args.kind} items")
    if not items:
        sys.exit(
            "No items — run the corresponding batch first (run_batch.py / run_tailor_batch.py)."
        )

    if not args.push:
        print("dry run; first item:")
        print(json.dumps(items[0], indent=2, ensure_ascii=False)[:2000])
        return

    dataset = client.get_or_create_dataset(dataset_name, description=description)
    dataset.insert(items)  # Opik dedupes identical items — safe to re-run
    print(f"Pushed {len(items)} items to Opik dataset '{dataset_name}'.")


if __name__ == "__main__":
    main()
