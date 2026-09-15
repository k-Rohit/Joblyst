
from __future__ import annotations

import sys
from typing import Any
from datetime import UTC, datetime
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

def _find_spans(client, trace_id: str, name: str) -> list:
    spans = client.search_spans(project_name=_get_opik_project_name(), trace_id=trace_id, truncate=False)
    return [s for s in spans if getattr(s, "name", "") == name]

def _provenance(trace, span_id: str | None, tag: str) -> dict:
    return {
        "trace_id": str(trace.id),
        "thread_id": getattr(trace, "thread_id", None),
        "span_id": span_id,
        "source_tag": tag,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    

def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}

def build_ranking_items(client, max_items):
    """One item per ranked job, sampled from the traces' final state.

    The trace OUTPUT carries the final graph state (profile + the full sorted
    ``ranked_jobs``); per-trace we sample the best, middle, and worst-ranked
    job so the dataset spans the score range instead of exhausting one run.
    """
    
    
    