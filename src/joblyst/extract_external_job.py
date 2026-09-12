"""Turn a pasted job posting into a real JobPosting.

Only short, checkable facts (title/company/location/remote) come from the
LLM. ``description`` is assigned directly from the pasted text — never model
output — so it can't drift from what the poster actually wrote.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel
from langchain_core.messages import SystemMessage

from joblyst.config import get_settings
from joblyst.llm import get_chat_model
from joblyst.prompts.extract_external_job import EXTRACT_JOB_PROMPT
from joblyst.schemas.schemas import JobPosting


class _ExternalJobSchema(BaseModel):
    title: str
    company: str
    location: str
    remote: bool


def extract_external_job(job_text: str) -> JobPosting:
    """Extract structured fields from pasted job text and build a JobPosting."""
    settings = get_settings()
    model = get_chat_model(settings.joblyst_fetch_model, temperature=0.0).with_structured_output(_ExternalJobSchema)
    fields: _ExternalJobSchema = model.invoke([SystemMessage(EXTRACT_JOB_PROMPT.format(job_text=job_text))])  # type: ignore

    return JobPosting(
        job_id=f"external-{uuid4().hex[:8]}",
        title=fields.title,
        company=fields.company,
        location=fields.location,
        remote=fields.remote,
        description=job_text,
        url="",
        tags=[],
        source="cache",
    )


if __name__ == "__main__":
    text = input("Paste the job description: ")
    print(extract_external_job(text))
