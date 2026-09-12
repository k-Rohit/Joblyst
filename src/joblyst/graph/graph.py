from __future__ import annotations
from functools import lru_cache

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from joblyst.graph.state import AgentState
from joblyst.graph.nodes import fetch_jobs, rank_jobs, reformulate_query
from joblyst.graph.nodes.tailor import tailor
from joblyst.graph.nodes.validate_tailoring import validate_tailoring

GOOD_FIT_THRESHOLD = 60
MIN_GOOD_JOBS = 5
MAX_REFFORMULATIONS = 2

# routing functions -
def route_entry(state: AgentState) -> str:
    """Entry router: tailor a selected job, or run the job search.

    ``selected_job_id`` must be passed explicitly on every invocation (None
    for a search) — it persists on the thread, so omitting it after a
    tailoring run would route a fresh search into ``tailor`` against a stale
    job id left over from the previous call.
    """
    return "tailor" if state.get("selected_job_id") else "fetch_jobs"


def should_reformulate(state: AgentState) -> str:
    """ 
    Route after ranking: loop to broaden the search, or finish.
    
    find the number of good jobs (the jobs where the fit score is > 60) if the count of good jobs > MIN_GOOD_JOBS then we dont need to reformulate other wise we have to.
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

    builder.add_conditional_edges(START, route_entry, ["fetch_jobs", "tailor"])
    builder.add_edge("fetch_jobs","rank_jobs")
    builder.add_conditional_edges("rank_jobs", should_reformulate, ["reformulate_query", END])
    builder.add_edge("reformulate_query","fetch_jobs")
    builder.add_edge("tailor", "validate_tailoring")
    builder.add_edge("validate_tailoring", END)

    return builder.compile(checkpointer=checkpointer or MemorySaver())

@lru_cache(maxsize=1)
def get_compiled_graph():
    return _build_graph()


