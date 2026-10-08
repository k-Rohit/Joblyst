from uuid import UUID

from psycopg.types.json import Jsonb

from joblyst import db
from joblyst.schemas.schemas import Profile

_SESSIONS: dict[UUID, dict] = {}


def save(thread_id: UUID, cv_text: str, profile: Profile) -> None:
    if not db.is_open():
        _SESSIONS[thread_id] = {"cv_text": cv_text, "profile": profile}
        return
    with db.get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO candidate_sessions (thread_id, cv_text, profile) VALUES (%s, %s, %s)",
            (thread_id, cv_text, Jsonb(profile.model_dump(mode="json"))),
        )


def get(thread_id: UUID) -> dict | None:
    if not db.is_open():
        return _SESSIONS.get(thread_id)
    with db.get_pool().connection() as conn:
        row = conn.execute(
            "SELECT cv_text, profile FROM candidate_sessions WHERE thread_id = %s AND expires_at > now()",
            (thread_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "cv_text": row["cv_text"],
        "profile": Profile.model_validate(row["profile"]),
    }
