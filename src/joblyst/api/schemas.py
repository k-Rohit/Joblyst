from uuid import UUID

from pydantic import BaseModel

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


class TailorRequest(BaseModel):
    thread_id: UUID
    selected_job_id: str


class TailorResponse(BaseModel):
    thread_id: UUID
    pack: TailoringPack
    # Always present when there is a pack — validate_tailoring only returns None
    # when tailoring produced nothing. The flag count is fabrication_report.flags.
    fabrication_report: FabricationReport
