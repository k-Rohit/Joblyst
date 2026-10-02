"""Broaden the search query when too few good matches came back.

Increments the reformulation counter (the loop guard) and writes a new
``search_query`` that fetch_jobs will use as guidance on the next pass.
"""

from __future__ import annotations

from joblyst.config import get_settings
from joblyst.graph.nodes.fetch_jobs import _trim_query
from joblyst.graph.state import AgentState
from joblyst.llm import ensure_budget, get_chat_model
from joblyst.prompts.reformulate import REFORMULATE_PROMPT


def reformulate_query(state: AgentState) -> dict:
    """Ask the LLM for a broader search query and bump the loop counter."""
    settings = get_settings()
    calls = state.get("llm_calls", 0)
    ensure_budget(calls, 1, settings.max_llm_calls_per_run)
    profile = state["profile"]
    # extract_profile always runs before the graph starts, so this should never fire
    assert profile is not None, "reformulate_query requires profile to already be set"

    prompt = REFORMULATE_PROMPT.format(
        profile=", ".join(profile.primary_roles + profile.skills[:10]),
        previous_query=state.get("search_query") or "",
    )
    raw_query = get_chat_model(settings.joblyst_model, temperature=0.0).invoke(prompt).content.strip()
    # Same guard the fetch path applies to the model's own query. Without it a
    # reformulation like "Data Analyst OR Business Analyst OR SQL OR Excel OR ..."
    # reaches fetch_jobs as prompt guidance, which then splits it into one tool
    # call per term — 16 searches for one run (see engineering_log.md).
    new_query, dropped = _trim_query(raw_query)
    errors = list(state.get("errors", []))
    if dropped:
        errors.append(f"reformulate_query: query cut back to a single title, dropped {dropped!r}")

    return {
        "search_query": new_query,
        "errors": errors,
        "reformulation_count": state.get("reformulation_count", 0) + 1,
        "llm_calls": calls + 1,
    }