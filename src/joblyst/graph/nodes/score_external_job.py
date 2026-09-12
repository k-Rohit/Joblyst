"""
Score external job (the job that user has identified by himself/herself) not something which has come through the `fetch_jobs` function.

"""

from joblyst.config import get_settings
from joblyst.graph.nodes.rank_jobs import _render_profile, _render_jobs as _render_job, RANK_JOBS_PROMPT
from joblyst.extract_external_job import extract_external_job
from joblyst.graph.state import AgentState
from joblyst.llm import ensure_budget, get_chat_model
from joblyst.schemas.schemas import JobScores, RankedJob

def score_external_job(state: AgentState) -> dict:
    settings = get_settings()
    errors = list(state.get("errors", []))

    external_job_text = state.get("external_job_text", "")
    assert external_job_text

    profile = state.get("profile")
    assert profile is not None, "score_external_job requires profile to already be set"

    external_job = extract_external_job(external_job_text)
    rendered_job = _render_job([external_job])
    rendered_profile = _render_profile(profile)

    # extract_external_job already made 1 call (field extraction); this node's
    # own ranking call is the 2nd — budget both before spending either.
    calls = state.get("llm_calls", 0)
    ensure_budget(calls, 2, settings.max_llm_calls_per_run)

    model = get_chat_model(settings.joblyst_model, temperature=0.0).with_structured_output(JobScores)
    prompt = RANK_JOBS_PROMPT.format(profile=rendered_profile, jobs=rendered_job)
    scores: JobScores = model.invoke(prompt)  # type: ignore

    ranked = list(state.get("ranked_jobs", []))
    if scores.scores:
        score = scores.scores[0]
        ranked.append(
            RankedJob(
                job=external_job,
                fit_score=score.fit_score,
                fit_explanation=score.fit_explanation,
                matched_skills=score.matched_skills,
                gaps=score.gaps,
            )
        )
    else:
        errors.append("score_external_job: ranking LLM returned no score for the pasted job")

    return {
        "ranked_jobs": ranked,
        "selected_job_id": external_job.job_id,
        "llm_calls": calls + 2,
        "errors": errors,
    }

