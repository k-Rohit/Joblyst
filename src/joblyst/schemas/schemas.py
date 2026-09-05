"""
Pydantic models used across the agent graph.

These are the structured-output targets for the LLM/tool calls and the shared
data contracts the nodes read and write.
"""

from pydantic import BaseModel, Field
from typing import Literal

Seniority = Literal["junior", "mid", "senior", "lead", "unknown"]
JobSourceName = Literal["jsearch", "adzuna", "remotive", "cache"]

class Profile(BaseModel):
    """ A profile schema for a user in the joblyst application."""
    
    name: str | None = None
    seniority: Seniority = "unknown"
    primary_roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    years_experience: float | None = None
    locations: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    remote_ok: bool = False
    raw_summary: str = ""
    
    
    