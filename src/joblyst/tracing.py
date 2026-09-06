"""Opik instrumentation. Degrades to a no-op when tracing is off or unkeyed."""

from __future__ import annotations

from typing import Any

import contextlib
import subprocess
from collections.abc import Callable

from joblyst.config import get_settings

_CONFIGURED = False


def configure_opik() -> bool:
    """Configure the Opik SDK once. Returns True if tracing is active."""
    global _CONFIGURED
    settings = get_settings()
    if not settings.has_opik:
        return False
    if _CONFIGURED:
        return True
    import opik

    opik.configure(
        api_key=settings.opik_api_key.get_secret_value(),
        workspace=settings.opik_workspace or None,
        project_name=settings.opik_project_name,
        use_local=False,
        force=True,
    )
    _CONFIGURED = True
    return True


def get_tracer(thread_id: str, tags: list[str]):
    """Return an OpikTracer for this run, or None when tracing is disabled."""
    if not configure_opik():
        return None
    from opik.integrations.langchain import OpikTracer

    settings = get_settings()
    return OpikTracer(tags=tags, thread_id=thread_id, project_name=settings.opik_project_name)


def traced_call[T](name: str, fn: Callable[[], T], metadata: dict[str, Any] | None = None) -> Callable[[], T]:
    """Give ``fn`` its own span, named, or hand it back untouched.

    A trace that shows only the total search time cannot answer "which source
    was slow" — which is the first question anybody (Ollie included) asks of a
    waterfall. One span per source turns that guess into a reading.

    Untouched when tracing is off, deliberately: ``opik.track`` still tries to
    ship spans without an API key and answers 401 into the reader's terminal.
    Wrapping only when configured keeps the keyless path silent, which is the
    same promise the rest of this module makes.
    """
    if not configure_opik():
        return fn
    import opik
    return opik.track(name=name, type="tool", metadata=metadata, capture_input=False)(fn)