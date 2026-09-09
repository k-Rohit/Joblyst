"""Broaden the search query when too few good matches came back.

Increments the reformulation counter (the loop guard) and writes a new
``search_query`` that fetch_jobs will use as guidance on the next pass.
"""

from __future__ import annotations

from joblyst.config import get_settings
from joblyst.prompts.reformulate import REFORMULATE_PROMPT
from joblyst.graph.state import AgentState
from joblyst.llm import ensure_budget, get_chat_model


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
    new_query = get_chat_model(settings.joblyst_model, temperature=0.0).invoke(prompt).content.strip()

    return {
        "search_query": new_query,
        "reformulation_count": state.get("reformulation_count", 0) + 1,
        "llm_calls": calls + 1,
    }