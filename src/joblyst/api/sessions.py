from uuid import UUID

from joblyst.schemas.schemas import Profile

_SESSIONS: dict[UUID, dict] = {}


def save(thread_id: UUID, cv_text: str, profile: Profile) -> None:
    _SESSIONS[thread_id] = {"cv_text": cv_text, "profile": profile}


def get(thread_id: UUID) -> dict | None:
    return _SESSIONS.get(thread_id)
