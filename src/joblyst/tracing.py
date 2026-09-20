"""Opik instrumentation. Degrades to a no-op when tracing is off or unkeyed."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from joblyst.config import get_settings

logger = logging.getLogger(__name__)

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


def register_prompts() -> int:
    """Register every prompt in Opik's prompt library, so edits are versioned.

    Idempotent: unchanged text is a no-op, changed text becomes a new version.
    Returns how many prompts were synced (0 when tracing is off). A failure is
    logged, never raised — prompt sync must not block a run.
    """
    if not configure_opik():
        return 0
    import opik

    from joblyst.prompts.drift_check import DRIFT_CHECK_PROMPT, DRIFT_CHECK_PROMPT_NAME
    from joblyst.prompts.extact_profile_prompt import (
        EXTRACT_PROFILE_PROMPT,
        EXTRACT_PROFILE_PROMPT_NAME,
    )
    from joblyst.prompts.extract_external_job import (
        EXTRACT_JOB_PROMPT,
        EXTRACT_JOB_PROMPT_NAME,
    )
    from joblyst.prompts.rank_jobs import RANK_JOBS_PROMPT, RANK_JOBS_PROMPT_NAME
    from joblyst.prompts.reformulate import REFORMULATE_PROMPT, REFORMULATE_PROMPT_NAME
    from joblyst.prompts.tailor import TAILOR_PROMPT, TAILOR_PROMPT_NAME

    prompts = [
        (EXTRACT_PROFILE_PROMPT_NAME, EXTRACT_PROFILE_PROMPT),
        (EXTRACT_JOB_PROMPT_NAME, EXTRACT_JOB_PROMPT),
        (RANK_JOBS_PROMPT_NAME, RANK_JOBS_PROMPT),
        (REFORMULATE_PROMPT_NAME, REFORMULATE_PROMPT),
        (TAILOR_PROMPT_NAME, TAILOR_PROMPT),
        (DRIFT_CHECK_PROMPT_NAME, DRIFT_CHECK_PROMPT),
    ]
    client = opik.Opik()
    project = get_settings().opik_project_name
    synced = 0
    for name, text in prompts:
        try:
            # project_name scopes the prompt to the project, so it shows up in
            # that project's prompt library instead of only workspace-wide.
            client.create_prompt(name=name, prompt=text, project_name=project)
            synced += 1
        except Exception:
            logger.warning("could not register prompt %r in Opik", name, exc_info=True)
    return synced


def opik_url() -> str:
    """Best-effort dashboard link for the UI footer."""
    settings = get_settings()
    if settings.opik_workspace:
        return f"https://www.comet.com/opik/{settings.opik_workspace}/projects"
    return "https://www.comet.com/opik/"


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