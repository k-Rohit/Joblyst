"""Prompts live in Opik's prompt library, not in this repo.

Edit a prompt in Opik and the app picks up the new version: the Opik SDK caches
each prompt in memory and re-fetches it in the background every 5 minutes
(``OPIK_PROMPT_CACHE_TTL_SECONDS``). If Opik goes down while the app is running,
the cached copy keeps being used. A process that starts while Opik is
unreachable has no copy at all, so ``load_all()`` runs at server startup and
stops the server with a clear error instead of failing on the first request.

Placeholders are mustache, ``{{name}}``.
"""

from __future__ import annotations

import re
from functools import lru_cache

from joblyst.config import get_settings
from joblyst.exceptions import PromptUnavailableError
from joblyst.tracing import configure_opik

EXTRACT_PROFILE = "extract_profile"
EXTRACT_JOB = "extract_job_fields"
RANK_JOBS = "rank_jobs"
REFORMULATE = "reformulate"
TAILOR = "tailor_application"
TAILOR_RESEARCH_RULE = "tailor_research_rule"
DRIFT_CHECK = "drift_check"
FETCH_JOBS_SYSTEM = "fetch_jobs_system"

ALL = (EXTRACT_PROFILE, EXTRACT_JOB, RANK_JOBS, REFORMULATE, TAILOR, TAILOR_RESEARCH_RULE, DRIFT_CHECK, FETCH_JOBS_SYSTEM)

_PLACEHOLDER = re.compile(r"{{\s*([a-zA-Z_]\w*)\s*}}")


@lru_cache(maxsize=1)
def _client():
    if not configure_opik():
        raise PromptUnavailableError("Prompts are stored in Opik, but Opik is not configured. Set OPIK_API_KEY.")
    import opik

    return opik.Opik()


def get(name: str):
    """The latest version of a prompt, as an Opik ``Prompt`` (served from the SDK's cache)."""
    prompt = _client().get_prompt(name=name, project_name=get_settings().opik_project_name)
    if prompt is None:
        raise PromptUnavailableError(f"Prompt {name!r} was not found in Opik's prompt library.")
    return prompt


def render(name: str, **values: object) -> str:
    """Fill a prompt's placeholders.

    Opik leaves an unfilled ``{{name}}`` in the text instead of raising, which
    would send the bare placeholder to the LLM. So every placeholder must be
    given, and every value given must have a placeholder.
    """
    text = get(name).prompt
    wanted = set(_PLACEHOLDER.findall(text))
    missing, unused = wanted - values.keys(), values.keys() - wanted
    if missing or unused:
        raise PromptUnavailableError(
            f"Prompt {name!r} needs {sorted(wanted)}; missing {sorted(missing)}, not in the prompt {sorted(unused)}."
        )
    return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), text)


def load_all() -> None:
    """Fetch every prompt once, so a missing one stops startup with a clear error."""
    missing = []
    for name in ALL:
        try:
            get(name)
        except PromptUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 — any SDK network/auth error; all are re-raised below
            missing.append(f"{name} ({type(exc).__name__}: {exc})")
    if missing:
        raise PromptUnavailableError("Could not fetch prompts from Opik: " + "; ".join(missing))
