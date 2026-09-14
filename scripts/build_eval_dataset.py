
from __future__ import annotations

import sys
from typing import Any
from joblyst.config import get_settings

from joblyst.tracing import configure_opik

def _client():
    # check if opik has been configured - 
    if not configure_opik():
        sys.exit("Opik is not configured!")
    
    import opik
    return opik.Opik()

def _get_opik_project_name() -> str:
    settings = get_settings()
    return settings.opik_project_name

def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}

def build_ranking_items(client, max_items):
    """One item per ranked job, sampled from the traces' final state.

    The trace OUTPUT carries the final graph state (profile + the full sorted
    ``ranked_jobs``); per-trace we sample the best, middle, and worst-ranked
    job so the dataset spans the score range instead of exhausting one run.
    """
    
    