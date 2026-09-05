""" 
This module will fetch the jobs from the job boards
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol

import httpx
from langchain_core.tools import tool

from joblyst.config import get_settings
from joblyst.schemas.schemas import JobPosting

DESCRIPTION_LIMIT = 4000
DEFAULT_LIMIT = 25
DEFAULT_COUNTRY = "in"

CACHE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cached_jobs.json"

_COUNTRY_CODES: dict[str, str] = {
    "united states": "us", "usa": "us", "us": "us", "america": "us",
    "united kingdom": "gb", "uk": "gb", "england": "gb", "london": "gb",
    "germany": "de", "deutschland": "de", "berlin": "de", "munich": "de", "münchen": "de",
    "india": "in", "bengaluru": "in", "bangalore": "in", "mumbai": "in", "delhi": "in",
    "australia": "au", "sydney": "au", "melbourne": "au",
    "brazil": "br", "brasil": "br", "são paulo": "br", "sao paulo": "br",
    "canada": "ca", "france": "fr", "spain": "es", "netherlands": "nl",
    "singapore": "sg", "poland": "pl", "italy": "it",
}  # fmt: skip

logger = logging.getLogger(__name__)

def _location_to_country(location: str | None):
    if location is None:
        return DEFAULT_COUNTRY
    location = location.strip().lower()
    return _COUNTRY_CODES.get(location,DEFAULT_COUNTRY)

def _truncate(text: str) -> str:
    """Cap a description at ``DESCRIPTION_LIMIT`` characters."""
    return (text or "")[:DESCRIPTION_LIMIT]

def _failed(source: str, exc: Exception) -> list[JobPosting]: # type: ignore
    """Record why a source returned nothing, then return nothing.

    Every source used to answer an exhausted quota, a rejected key and a genuine
    zero-result search with the same empty list, which made the three
    indistinguishable from the outside. JSearch spent a week returning HTTP 429
    while the cascade quietly fell through to a worse board and nobody could
    tell, because "no jobs" is exactly what a working search looks like on a
    quiet day. The reason belongs somewhere a human will actually see it.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        hint = {401: "key rejected", 403: "key lacks access", 429: "quota exhausted"}.get(code, "")
        reason = f"HTTP {code}{f' ({hint})' if hint else ''}"
    elif isinstance(exc, httpx.TimeoutException):
        reason = "timed out"
    else:
        reason = type(exc).__name__
        logger.warning("job source %s returned no jobs: %s", source, reason)
        return []

class JobSource(Protocol):
    """A pluggable jobs backend.

    Adapters must never raise on a network or parse error; they return an empty
    list so ``run_search`` can fall through to the next source.
    """

    name: str

    def fetch(self, query: str, location: str | None, country: str | None, remote: bool, limit: int) -> list[JobPosting]:
        """Return postings matching the query, or an empty list on any failure."""
        ...
    
class JSearchSource:
    
    """
    Official Google-for-Jobs aggregator (OpenWeb Ninja) with city-level search.

    Location is honoured deterministically: the location is folded into the query
    (``"<query> in <location>"``) and the country code is derived from it, so a
    Berlin CV returns Berlin jobs regardless of how the query was phrased.
    """
    
    name = "jsearch"
    BASE = "https://api.openwebninja.com/jsearch/search-v2"
    
    def __init__(self, api_key: str = "", timeout: float = 15.0) -> None:
        self.api_key = api_key or get_settings().jsearch_api_key.get_secret_value()
        self.timeout = timeout
    
    @property
    def available(self) -> bool:
        """Whether an API key is configured."""
        return bool(self.api_key)
    
    def fetch(self, query: str, location: str | None, country: str | None, remote: bool, limit: int) -> list[JobPosting]:
        """Fetch one page (10 results = 1 request credit; the free tier is small)."""
        if not self.available:
            return []
        
        params: dict[str, object] = {
            "query": f"{query} in {location}" if location else query,
            "country": country or _location_to_country(location),
            "num_pages": 1,
        }
        
        if remote:
            params["work_from_home"] = "true"
        try:
            response = httpx.get(self.BASE, params=params, headers={"X-API-Key": self.api_key}, timeout=self.timeout) # type: ignore
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as e:
            return _failed(self.name, e)
        payload = data.get("data")
        rows = payload.get("jobs") if isinstance(payload, dict) else payload if isinstance(payload, list) else []
        return [self._to_posting(r) for r in (rows or [])[:limit]]
    
    @staticmethod
    def _clean_location(r: dict) -> str:
        """Extract the location from JSearch, dropping the ``• via <publisher>`` suffix."""
        raw = (r.get("job_location") or "").split("•")[0].strip()
        if raw:
            return raw
        parts = [r.get("job_city"), r.get("job_state"), r.get("job_country")]
        return ", ".join(p for p in parts if p) or "Unspecified"

    @staticmethod
    def _to_posting(r: dict) -> JobPosting:
        """Convert one JSearch result into a ``JobPosting``."""
        return JobPosting(
            job_id=f"jsearch-{r.get('job_id') or r.get('id', '')}",
            title=(r.get("job_title") or "").strip() or "Untitled",
            company=(r.get("employer_name") or "").strip() or "Unknown",
            location=JSearchSource._clean_location(r),
            remote=bool(r.get("job_is_remote")),
            description=_truncate(r.get("job_description") or ""),
            url=r.get("job_apply_link") or "",
            tags=[t for t in [r.get("job_employment_type"), r.get("job_publisher")] if t],
            source="jsearch",
    )

class AdzunaSource:
    """ 
    Free official jobs API covering ~20 countries; needs an app id and key.
    """
    name = "adzuna"
    BASE = "https://api.adzuna.com/v1/api/jobs"

    def __init__(self, app_id: str = "", app_key: str = "", timeout: float = 10.0) -> None:
        settigs = get_settings()
        self.app_id = app_id or settigs.adzuna_app_id.get_secret_value()
        self.app_key = app_key or settigs.adzuna_api_key.get_secret_value()
        self.timeout = timeout
    
    @property
    def available(self) -> bool:
        """Whether an API key is configured."""
        return bool(self.app_key) 
    
    def fetch(self, query: str, location: str | None, country: str | None, remote: bool, limit: int) -> list[JobPosting]:
        if not self.available:
            return []
        code = country or _location_to_country(country)
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": min(limit, 50),
            "what": query,
            "content-type": "application/json",
        }
        if location:
            params["where"] = location
        
        try:
            resp = httpx.get(f"{self.BASE}/{code}/search/1", params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            return _failed("adzuna", exc)
        return [self._to_posting(r, code) for r in data.get("results", [])]
    
    @staticmethod
    def _to_posting(r: dict, code: str) -> JobPosting:
        """Convert one Adzuna result into a ``JobPosting``."""
        loc = (r.get("location") or {}).get("display_name") or code.upper()
        return JobPosting(
            job_id=f"adzuna-{r.get('id', '')}",
            title=r.get("title", "").strip() or "Untitled",
            company=(r.get("company") or {}).get("display_name", "").strip() or "Unknown",
            location=loc,
            remote="remote" in (r.get("title", "") + loc).lower(),
            description=_truncate(r.get("description", "")),
            url=r.get("redirect_url", ""),
            tags=[c.get("label", "") for c in [r.get("category", {})] if c.get("label")],
            source="adzuna",
        )
        
class RemotiveSource:
    """Keyless API of worldwide remote jobs."""

    name = "remotive"
    BASE = "https://remotive.com/api/remote-jobs"

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def fetch(self, query: str, location: str | None, country: str | None, remote: bool, limit: int) -> list[JobPosting]:
        """Fetch remote postings matching the query."""
        try:
            resp = httpx.get(self.BASE, params={"search": query, "limit": limit}, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            return _failed("remotive", exc)
        return [self._to_posting(r) for r in data.get("jobs", [])[:limit]]

    @staticmethod
    def _to_posting(r: dict) -> JobPosting:
        """Convert one Remotive result into a ``JobPosting``."""
        return JobPosting(
            job_id=f"remotive-{r.get('id', '')}",
            title=r.get("title", "").strip() or "Untitled",
            company=r.get("company_name", "").strip() or "Unknown",
            location=r.get("candidate_required_location") or "Remote",
            remote=True,
            description=_truncate(r.get("description", "")),
            url=r.get("url", ""),
            tags=r.get("tags", []) or [],
            source="remotive",
        )
        


    

    
    

