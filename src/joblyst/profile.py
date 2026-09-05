from joblyst.llm import get_chat_model
from joblyst.schemas.schemas import Profile
from joblyst.prompts.prompt import EXTRACT_PROFILE_PROMPT

from joblyst.tracing import get_tracer

from joblyst.config import get_settings

settings = get_settings()

def extract_profile(cv_text: str, *, thread_id: str | None, tags: list[str] | None = None, model: str | None = None) -> Profile:
    llm = get_chat_model(model or settings.llm_model, temperature=0.0).with_structured_output(Profile)
    
    tracer = get_tracer(thread_id, tags or ["extract"]) if thread_id else None
    config = {"callbacks": [tracer]} if tracer else {}
    
    profile: Profile = llm.invoke(EXTRACT_PROFILE_PROMPT.format(cv_text=cv_text), config=config) # type: ignore
    if tracer:
        tracer.flush()
    return profile
    
    
    


