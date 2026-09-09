""" 
Score each fetched job against the profile of the user.
This happens in batches (default = 4 i.e 4 jobs per llm call to rank)

The LLM returns lean ``JobScore`` objects keyed by ``job_id``; we pair each back
to its ``JobPosting`` to build a ``RankedJob``.

"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

from joblyst.config import get_settings
from joblyst.prompts.rank_jobs import RANK_JOBS_PROMPT
from joblyst.schemas.schemas import JobScores, JobPosting, Profile, RankedJob
from joblyst.graph.state import AgentState
from joblyst.llm import get_chat_model, ensure_budget

MAX_PARALLEL_BATCHES = 4

def _render_profile(profile: Profile) -> str:
    """Format the profile as plain text for the ranking prompt."""
    return (
        f"Name: {profile.name}\n"
        f"Seniority: {profile.seniority}\n"
        f"Roles: {', '.join(profile.primary_roles)}\n"
        f"Skills: {', '.join(profile.skills)}\n"
        f"Years experience: {profile.years_experience}\n"
        f"Locations: {', '.join(profile.locations)}\n"
        f"Remote ok: {profile.remote_ok}"
    )

def _render_jobs(jobs: list[JobPosting]) -> str:
    """Format a batch of jobs as plain text for the ranking prompt."""
    return "\n\n---\n\n".join(
        f"job_id: {job.job_id}\n"
        f"title: {job.title}\n"
        f"company: {job.company}\n"
        f"location: {job.location} (remote: {job.remote})\n"
        f"description: {job.description[:1500]}"
        for job in jobs
    )
    
def _batches(items: list[JobPosting], size: int) -> Iterator[list[JobPosting]]:
    """Yield ``items`` in chunks of ``size``."""
    for i in range(0, len(items), size):
        yield items[i : i + size]

def rank_jobs(state: AgentState) -> dict:
    """  
    Score each fetched job against the profile and return them sorted by fit.
    Jobs already scored in a previous pass (reformulation loops merge new
    fetches into ``state["jobs"]``), so the older jobs keep their scores — the profile hasn't
    changed, so re-scoring them would only re-spend the same LLM calls. Only
    genuinely new postings go to the model.
    """
    
    settings = get_settings()
    profile = state.get("profile")
    jobs = state.get("jobs",[])
    if not jobs:
        return {"ranked_jobs":[]}

    ranked: list[RankedJob] = list(state.get("ranked_jobs",[]) or [])
    already_scored = {r.job.job_id for r in ranked}
    to_score = [job for job in jobs if job.job_id not in already_scored]
    if not to_score:
        ranked.sort(key=lambda r: r.fit_score, reverse=True)
        return {"ranked_jobs": ranked}
    
    by_id = {job.job_id: job for job in to_score}
    calls = state.get("llm_calls", 0)
    batch_size = settings.joblyst_rank_batch
    # ceiling division: a trailing partial batch (e.g. 2 leftover jobs) still
    # costs one full LLM call, so plain // would undercount calls and let
    # ensure_budget pass on a wrong, too-low prediction.
    n_batches = (len(to_score) + batch_size - 1) // batch_size
    ensure_budget(calls, n_batches, settings.max_llm_calls_per_run)
    
    model = get_chat_model(settings.joblyst_model, temperature=0.0).with_structured_output(JobScores)
    
    def score_batch(batch: list[JobPosting]) -> JobScores:
        
        prompt = RANK_JOBS_PROMPT.format(profile=_render_profile(profile), jobs=_render_jobs(batch))  # type:ignore
        return model.invoke(prompt) # type:ignore
    
    # Batches are independent, so they run concurrently — ranking latency is the
    # slowest batch, not the sum. copy_context() carries LangChain's callback
    # contextvars into the worker threads, so Opik spans and token/cost tracking
    # still attach to the run.
    
    # here we are using copy_context because we are processing in batches but each batch is part of the same run  so the cost and other metrics must be part of same run/thread
    
    batches = list(_batches(to_score, batch_size))
    if len(batches) == 1:
        results = [score_batch(batches[0])]
    else:
        with ThreadPoolExecutor(max_workers=min(len(batches), MAX_PARALLEL_BATCHES)) as pool:
            futures = [pool.submit(contextvars.copy_context().run, score_batch, batch) for batch in batches]
            results = [future.result() for future in futures]
    calls += len(batches)
    
    for result in results:
        for score in result.scores:
            job = by_id.get(score.job_id)
            if job is None:
                continue
            ranked.append(
            RankedJob(
                job=job,
                fit_score=score.fit_score,
                fit_explanation=score.fit_explanation,
                matched_skills=score.matched_skills,
                gaps=score.gaps,
        )
    )
    
    ranked.sort(key=lambda r: r.fit_score, reverse=True)
    return {"ranked_jobs": ranked, "llm_calls": calls}

    
    
    
    
    
    
    
    
    
    