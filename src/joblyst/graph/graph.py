from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

from joblyst.graph.nodes import fetch_jobs, rank_jobs, reformulate_query
from joblyst.graph.nodes.score_external_job import score_external_job
from joblyst.graph.nodes.tailor import tailor
from joblyst.graph.nodes.validate_tailoring import validate_tailoring
from joblyst.graph.state import AgentState

GOOD_FIT_THRESHOLD = 60
MIN_GOOD_JOBS = 5
MAX_REFFORMULATIONS = 2

# Our Pydantic schemas, explicitly allow-listed for checkpoint (de)serialization —
# MemorySaver's default serde warns on (and will eventually block) unregistered
# custom types coming back out of a checkpoint.
_CHECKPOINT_TYPES = [
    ("joblyst.schemas.schemas", name)
    for name in (
        "Profile",
        "JobPosting",
        "RankedJob",
        "TailoredBullet",
        "ExperienceEntry",
        "ProjectEntry",
        "CVContent",
        "TailoringPack",
        "FlaggedClaim",
        "FabricationReport",
    )
]


def _checkpointer() -> MemorySaver:
    return MemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_TYPES))

# routing functions -
def route_entry(state: AgentState) -> str:
    """Entry router: tailor a selected job, or run the job search.

    ``selected_job_id`` must be passed explicitly on every invocation (None
    for a search) — it persists on the thread, so omitting it after a
    tailoring run would route a fresh search into ``tailor`` against a stale
    job id left over from the previous call. Checked first so an explicit
    tailor request always wins over a stray ``external_job_text``.
    """
    if state.get("selected_job_id"):
        return "tailor"
    if state.get("external_job_text"):
        return "score_external_job"
    return "fetch_jobs"


def should_reformulate(state: AgentState) -> str:
    """
    Route after ranking: loop to broaden the search, or finish.

    Count the good jobs (fit_score >= GOOD_FIT_THRESHOLD, so exactly 60 counts).
    Reformulate only when BOTH are true: fewer than MIN_GOOD_JOBS good ones, and
    we are still under MAX_REFFORMULATIONS. The second condition is what ends the
    run for a candidate who never reaches the bar — without it the loop would
    keep searching until the LLM budget raised instead.
    """

    ranked_jobs = state.get("ranked_jobs",[])
    reformulation_count = state.get("reformulation_count",0)
    good_jobs = sum(1 for r in ranked_jobs if r.fit_score >= GOOD_FIT_THRESHOLD)
    if good_jobs < MIN_GOOD_JOBS and reformulation_count < MAX_REFFORMULATIONS:
        return "reformulate_query"
    return END

def _build_graph(checkpointer: MemorySaver | None = None):
    "Build and compile the job-finding + tailoring graph"
    builder = StateGraph(AgentState)
    builder.add_node("fetch_jobs", fetch_jobs)
    builder.add_node("rank_jobs", rank_jobs)
    builder.add_node("reformulate_query", reformulate_query)
    builder.add_node("tailor", tailor)
    builder.add_node("validate_tailoring", validate_tailoring)
    builder.add_node("score_external_job", score_external_job)

    builder.add_conditional_edges(START, route_entry, ["fetch_jobs", "tailor", "score_external_job"])
    builder.add_edge("fetch_jobs","rank_jobs")
    builder.add_conditional_edges("rank_jobs", should_reformulate, ["reformulate_query", END])
    builder.add_edge("reformulate_query","fetch_jobs")
    builder.add_edge("score_external_job", "tailor")
    builder.add_edge("tailor", "validate_tailoring")
    builder.add_edge("validate_tailoring", END)

    return builder.compile(checkpointer=checkpointer or _checkpointer())

@lru_cache(maxsize=1)
def get_compiled_graph():
    return _build_graph()


