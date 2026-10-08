"""One Postgres connection pool for the whole app.

Shared by the session store and LangGraph's checkpointer.
"""

from __future__ import annotations

from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

from joblyst.config import get_settings

_pool: ConnectionPool[Connection[DictRow]] | None = None


def open_pool():
    """Create and open the pool. Does nothing if DATABASE_URL isn't set, or if it's already open."""
    global _pool
    url = get_settings().database_url
    if url is None or _pool is not None:
        return

    _pool = ConnectionPool(
        conninfo=url.get_secret_value(),
        # Tells the type checker these connections return dict rows; the
        # row_factory below is what does it at runtime. LangGraph's checkpointer
        # also requires exactly this type.
        connection_class=Connection[DictRow],
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        min_size=1,
        max_size=5,
        open=False,
    )
    # wait = True; Check the database really connects before the server starts.
    # If the password or URL is wrong, the server won't start at all.
    _pool.open(wait=True, timeout=30)


def close_pool() -> None:
    """Close the pool on shutdown, so connections are returned to Supabase cleanly."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_pool() -> ConnectionPool[Connection[DictRow]]:
    """The open pool. Fails loudly if it was never opened, rather than returning None."""
    if _pool is None:
        raise RuntimeError(
            "Database pool is not open. Is DATABASE_URL set, and was open_pool() called at startup?"
        )
    return _pool


def is_open() -> bool:
    return _pool is not None
