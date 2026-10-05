from uuid import UUID

from pydantic import BaseModel

from joblyst.schemas.schemas import Profile, RankedJob


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
