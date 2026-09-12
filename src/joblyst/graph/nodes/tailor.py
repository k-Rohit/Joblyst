"""
Tailor an application for one selected already ranked job.

This node runs as a SECOND invocation on the same check and everything else — ``profile``, ``ranked_jobs``,
``cv_text`` — is read from the thread's checkpoint. Nothing re-runs.

The candidate corpus is recomputed here from the checkpointed ``cv_text`` 

Guards never raise: a missing search state or an unknown job id is recorded in
``errors`` (visible in the trace span) and the node returns ``tailoring: None``.
"""

from __future__ import annotations

from joblyst.config import get_settings
from joblyst.corpus import build_corpus
from joblyst.graph.nodes.rank_jobs import _render_profile
from joblyst.schemas.schemas import RankedJob, TailoringPack
from joblyst.graph.state import AgentState
from joblyst.llm import get_chat_model, ensure_budget

_DESCRIPTION_LIMIT = 3000

def _render_job(ranked: RankedJob) -> str:
    """Format the target job (including its ranking context) for the prompt."""
    job = ranked.job
    return (
        f"title: {job.title}\n"
        f"company: {job.company}\n"
        f"location: {job.location} (remote: {job.remote})\n"
        f"fit_score: {ranked.fit_score} — {ranked.fit_explanation}\n"
        f"description: {job.description[:_DESCRIPTION_LIMIT]}"
    )
    
def tailor(state: AgentState) -> dict:
    return {}
