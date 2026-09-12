"""Company research for the tailor node (optional — only runs if Tavily is configured).

Grounds cover-letter company facts in something real instead of the model's
guess. Like the job sources, this must never raise: a failed lookup just means
the cover letter skips company-specific claims, not a broken tailoring run.
"""

from __future__ import annotations

import logging

import httpx

from joblyst.config import get_settings

_TAVILY_URL = "https://api.tavily.com/search"
_MAX_RESULTS = 3
_SNIPPET_LIMIT = 500

logger = logging.getLogger(__name__)


def research_company(company: str, timeout_s: float = 10.0) -> str | None:
    """Return a short text summary of ``company``, or None if research is unavailable."""
    settings = get_settings()
    if not settings.has_tavily:
        return None

    try:
        response = httpx.post(
            _TAVILY_URL,
            headers={"Authorization": f"Bearer {settings.tavily_api_key.get_secret_value()}"},
            json={
                "query": f"{company} company overview products",
                "max_results": _MAX_RESULTS,
                "search_depth": "basic",
            },
            timeout=timeout_s,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Tavily research for %r failed: %s", company, exc)
        return None

    results = data.get("results", [])
    if not results:
        return None

    # Join the top few result snippets into one plain-text block for the
    # tailor prompt — no need for titles/urls, just grounded facts to draw from.
    snippets = [r.get("content", "")[:_SNIPPET_LIMIT] for r in results if r.get("content")]
    return "\n\n".join(snippets) or None
