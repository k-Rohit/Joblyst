"""The LangGraph state schema passed onto every node."""

from typing import TypedDict

from joblyst.schemas.schemas import (
    FabricationReport,
    JobPosting,
    Profile,
    RankedJob,
    TailoringPack,
)


class AgentState(TypedDict):
    """The LangGraph state schema passed onto every node."""

    cv_text: str
    profile: Profile | None
    search_query: str | None
    jobs: list[JobPosting]
    ranked_jobs: list[RankedJob]
    reformulation_count: int
    llm_calls: int
    errors: list[str]
    jobs_sources: list[str]
    tailoring: TailoringPack | None
    selected_job_id: str | None
    external_job_text: str | None
    # added for the purpose of that sometimes a person may want to swtich domain/field.
    target_role: str | None
    # this list will contain the history of all the queries that has been used by the agent to search the job boards.
    searched_queries: list[str]
    research_notes: str | None
    fabrication_flags: int
    fabrication_report: FabricationReport | None
