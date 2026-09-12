"""One orchestration path for running the graph.

The whole point of sharing one compiled graph across search, tailor, and
external-job scoring is a single Opik thread: every entry point below takes
the SAME ``thread_id`` and passes it to both the LangGraph checkpointer
(``config["configurable"]["thread_id"]``) and the Opik tracer
(``get_tracer(thread_id, ...)``). Call ``run_search`` and later ``run_tailor``
with the same ``thread_id`` string, and Opik's dashboard shows both runs
grouped under one thread — the whole product, not three disconnected traces.

Tracing is passed in via ``config["callbacks"]`` on each call, not injected
into the compiled graph itself — the compiled graph is shared and cached
(``get_compiled_graph``), so baking a tracer into it would pin the FIRST
call's thread_id onto every later call sharing that same graph object.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from joblyst.graph.graph import get_compiled_graph
from joblyst.schemas.schemas import FabricationReport, Profile, RankedJob, TailoringPack
from joblyst.tracing import get_tracer


def _invoke(inputs: dict, *, thread_id: str, tags: list[str]) -> dict:
    """Shared plumbing: build a tracer, invoke the graph, flush, return final state."""
    tracer = get_tracer(thread_id, tags)
    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [tracer] if tracer else [],
    }
    final = get_compiled_graph().invoke(inputs, config=config)
    if tracer:
        tracer.flush()
    return final


@dataclass
class SearchResult:
    """The outcome of one job-search run."""

    profile: Profile | None = None
    ranked_jobs: list[RankedJob] = field(default_factory=list)
    jobs_sources: list[str] = field(default_factory=list)
    reformulation_count: int = 0
    errors: list[str] = field(default_factory=list)


def run_search(profile: Profile, cv_text: str, *, thread_id: str, tags: list[str] | None = None) -> SearchResult:
    """Run the job-search half of the graph for an already-extracted profile.

    ``selected_job_id`` is passed explicitly as None so a reused thread never
    routes into stale tailoring (see ``route_entry`` in graph.py).
    """
    inputs = {"profile": profile, "cv_text": cv_text, "selected_job_id": None}
    final = _invoke(inputs, thread_id=thread_id, tags=tags or ["search"])

    return SearchResult(
        profile=final.get("profile"),
        ranked_jobs=final.get("ranked_jobs", []),
        jobs_sources=final.get("jobs_sources", []),
        reformulation_count=final.get("reformulation_count", 0),
        errors=final.get("errors", []),
    )


@dataclass
class TailorResult:
    """The outcome of one tailoring run (a second invocation on a search thread)."""

    pack: TailoringPack | None = None
    fabrication_flags: int = 0
    fabrication_report: FabricationReport | None = None
    ranked_jobs: list[RankedJob] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run_tailor(*, thread_id: str, selected_job_id: str, tags: list[str] | None = None) -> TailorResult:
    """Run the tailoring half on an EXISTING search thread.

    Only ``selected_job_id`` is passed in — profile, ranked_jobs, and cv_text
    all come from the thread's checkpoint (the same thread_id run_search used),
    so nothing re-runs. Use the SAME thread_id here as the search that found
    this job, so Opik groups both under one thread.
    """
    inputs = {"selected_job_id": selected_job_id}
    final = _invoke(inputs, thread_id=thread_id, tags=tags or ["tailor"])

    return TailorResult(
        pack=final.get("tailoring"),
        fabrication_flags=final.get("fabrication_flags", 0),
        fabrication_report=final.get("fabrication_report"),
        ranked_jobs=final.get("ranked_jobs", []),
        errors=final.get("errors", []),
    )


def run_external_job(*, thread_id: str, external_job_text: str, tags: list[str] | None = None) -> TailorResult:
    """Score a pasted job, then tailor + validate for it — one call, one thread.

    Reuses an EXISTING thread's checkpointed profile/cv_text (from a prior
    run_search on the same thread_id), same as run_tailor. If no search ever
    ran on this thread, ``score_external_job`` records that in ``errors``.
    """
    inputs = {"external_job_text": external_job_text, "selected_job_id": None}
    final = _invoke(inputs, thread_id=thread_id, tags=tags or ["external_job"])

    return TailorResult(
        pack=final.get("tailoring"),
        fabrication_flags=final.get("fabrication_flags", 0),
        fabrication_report=final.get("fabrication_report"),
        ranked_jobs=final.get("ranked_jobs", []),
        errors=final.get("errors", []),
    )
