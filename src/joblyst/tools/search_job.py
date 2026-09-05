""" 
This module will fetch the jobs from the job boards
"""
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
    
   
if __name__ == "__main__":
    print(_location_to_country("são paulo"))
    
    

