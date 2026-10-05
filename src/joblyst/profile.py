from datetime import UTC, datetime

from joblyst.config import get_settings
from joblyst.llm import get_chat_model
from joblyst.prompts.extact_profile_prompt import EXTRACT_PROFILE_PROMPT
from joblyst.schemas.schemas import Profile
from joblyst.tracing import get_tracer

settings = get_settings()


def extract_profile(
    cv_text: str,
    *,
    thread_id: str | None,
    tags: list[str] | None = None,
    model: str | None = None,
) -> Profile:
    llm = get_chat_model(
        model or settings.llm_model, temperature=0.0
    ).with_structured_output(Profile)

    tracer = get_tracer(thread_id, tags or ["extract"]) if thread_id else None
    config = {"callbacks": [tracer]} if tracer else {}

    # The model's own clock is frozen at its training cutoff (gpt-4o-mini answers
    # "October 2023"), so every "2022 - Present" range was being computed against
    # that year and understated by ~3 years. Passing the real date fixes it and
    # cannot go stale.
    prompt = EXTRACT_PROFILE_PROMPT.format(
        cv_text=cv_text, today=datetime.now(UTC).date().isoformat()
    )
    profile: Profile = llm.invoke(prompt, config=config)  # type: ignore
    if tracer:
        tracer.flush()
    return profile
