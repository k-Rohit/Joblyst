from uuid import UUID

from pydantic import BaseModel, Field

from joblyst.schemas.schemas import FabricationReport, Profile, RankedJob, TailoringPack


class SearchRequest(BaseModel):
    thread_id: UUID
    locations: list[str]
    remote_ok: bool = False
    target_role: str | None = None


class SearchResponse(BaseModel):
    thread_id: UUID
    jobs: list[RankedJob]
    sources: list[str]
    reformulation_count: int


class ProfileResponse(BaseModel):
    thread_id: UUID
    profile: Profile
    # Role headings copied from the CV (corpus.work_history), not LLM output.
    experience: list[str] = Field(default_factory=list)


class TailorRequest(BaseModel):
    thread_id: UUID
    selected_job_id: str


class TailorResponse(BaseModel):
    thread_id: UUID
    pack: TailoringPack
    # Always present when there is a pack — validate_tailoring only returns None
    # when tailoring produced nothing. The flag count is fabrication_report.flags.
    fabrication_report: FabricationReport
    # corpus_ref -> the original CV line that tailored bullet was rewritten from,
    # so the user can compare the two.
    sources: dict[str, str] = Field(default_factory=dict)


class ExternalJobRequest(BaseModel):
    thread_id: UUID
    job_desc: str = Field(
        ..., min_length=100, description="Job description for the external job"
    )
