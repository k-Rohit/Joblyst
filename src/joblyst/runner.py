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

from collections.abc import Iterator
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


def _search_inputs(profile: Profile, cv_text: str, target_role: str | None) -> dict:
    """The graph inputs for a new search, shared by run_search and stream_search.

    Every per-search field is reset, because a new search must start fresh
    rather than continue the last one on this thread.
    """
    return {
        "profile": profile,
        "cv_text": cv_text,
        "selected_job_id": None,
        "target_role": target_role,
        "jobs": [],
        "ranked_jobs": [],
        "jobs_sources": [],
        "search_query": None,
        "reformulation_count": 0,
        "llm_calls": 0,
        "errors": [],
        "external_job_text": None,
    }


def run_search(
    profile: Profile,
    cv_text: str,
    *,
    thread_id: str,
    tags: list[str] | None = None,
    target_role: str | None = None,
) -> SearchResult:
    """Run the job-search half of the graph for an already-extracted profile.

    ``selected_job_id`` is passed explicitly as None so a reused thread never
    routes into stale tailoring (see ``route_entry`` in graph.py).
    """
    inputs = _search_inputs(profile, cv_text, target_role)
    final = _invoke(inputs, thread_id=thread_id, tags=tags or ["search"])
    return _to_search_result(final)


def stream_search(
    profile: Profile,
    cv_text: str,
    *,
    thread_id: str,
    tags: list[str] | None = None,
    target_role: str | None = None,
) -> Iterator[tuple[str, dict]]:
    """Run a search like ``run_search``, handing out each node's update as it finishes.

    Yields ``(node_name, update)``, where ``update`` holds only the fields that
    node changed. Once the loop ends, read the finished search with
    ``search_result(thread_id)``.
    """
    inputs = _search_inputs(profile, cv_text, target_role)
    tracer = get_tracer(thread_id, tags or ["search"])
    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [tracer] if tracer else [],
    }
    try:
        for chunk in get_compiled_graph().stream(inputs, config=config, stream_mode="updates"):
            for node, update in chunk.items():
                yield node, update or {}
    finally:
        # Runs even if the client disconnects mid-search, so the trace still reaches Opik.
        if tracer:
            tracer.flush()


def search_result(thread_id: str) -> SearchResult:
    """The finished search on this thread, read back from the graph's checkpoint."""
    state = get_compiled_graph().get_state({"configurable": {"thread_id": thread_id}})
    return _to_search_result(state.values)


def _to_search_result(final: dict) -> SearchResult:
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


def run_tailor(
    *, thread_id: str, selected_job_id: str, tags: list[str] | None = None
) -> TailorResult:
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


def run_external_job(
    profile: Profile,
    cv_text: str,
    *,
    thread_id: str,
    external_job_text: str,
    tags: list[str] | None = None,
) -> TailorResult:
    """Score a pasted job, then tailor + validate for it — one call, one thread.

    Takes the profile and CV text explicitly, like ``run_search``, so pasting a
    job works on a thread where no search has run. It used to read both from the
    checkpoint, which only a search fills — so "upload a CV, then paste a job"
    crashed on ``score_external_job``'s profile assert.
    """
    inputs = {
        "profile": profile,
        "cv_text": cv_text,
        "external_job_text": external_job_text,
        "selected_job_id": None,
    }
    final = _invoke(inputs, thread_id=thread_id, tags=tags or ["external_job"])

    return TailorResult(
        pack=final.get("tailoring"),
        fabrication_flags=final.get("fabrication_flags", 0),
        fabrication_report=final.get("fabrication_report"),
        ranked_jobs=final.get("ranked_jobs", []),
        errors=final.get("errors", []),
    )
