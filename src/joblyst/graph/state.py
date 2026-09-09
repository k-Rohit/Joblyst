""" The LangGraph state schema passed onto every node. """

from typing import TypedDict

from joblyst.schemas.schemas import FabricationReport, JobPosting, Profile, RankedJob, TailoringPack

class AgentState(TypedDict):
    """ The LangGraph state schema passed onto every node. """
    
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
    research_notes: str | None
    fabrication_flags: int
    fabrication_report: FabricationReport | None