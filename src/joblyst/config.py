"""Application configuration, loaded once from the environment / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    joblyst_fetch_model: str = Field(default="openai:gpt-4.1-nano", alias="JOBLYST_FETCH_MODEL")
    joblyst_model: str = Field(default="", alias="JOBLYST_MODEL")
    
    openai_api_key: SecretStr = Field(default=SecretStr(""), alias="OPENAI_API_KEY")
    llm_model: str = "openai:gpt-4o-mini"

    opik_api_key: SecretStr = Field(default=SecretStr(""), alias="OPIK_API_KEY")
    opik_workspace: str = Field(default="", alias="OPIK_WORKSPACE")
    opik_project_name: str = Field(default="joblyst", alias="OPIK_PROJECT_NAME")
    opik_enabled: bool = Field(default=True, alias="OPIK_ENABLED")
    
    resume_dir: str = './data'
    
    jsearch_api_key: SecretStr = Field(default=SecretStr(""), alias="JSEARCH_API_KEY")
    adzuna_app_id: SecretStr = Field(default=SecretStr(""), alias="ADZUNA_APP_ID")
    adzuna_api_key: SecretStr = Field(default=SecretStr(""), alias="ADZUNA_APP_KEY")
    jooble_api_key: SecretStr = Field(default=SecretStr(""), alias="JOOBLE_API_KEY")
    jooble_base_url: str = Field(default="https://jooble.org/api", alias="JOOBLE_BASE_URL")
    
    search_concurrent_sources: bool = Field(default=True, alias="SCOUT_CONCURRENT_SOURCES")
    joblyst_source_soft_deadline: float = Field(
        default=1.0,
        alias="JOBLYST_SOURCE_SOFT_DEADLINE",
        description="Seconds to wait for the first concurrent source before falling through to faster ones.",
    )
    joblyst_max_jobs: int = Field(
        default=10,
        alias="JOBLYST_MAX_JOBS",
        description="Jobs fetched per search call; drives ranking latency (more jobs = more rank_jobs batches).",
    )
    joblyst_rank_batch: int = Field(
        default=4,
        alias="JOBLYST_RANK_BATCH",
        description="Jobs scored per ranking LLM call; batches run in parallel.",
    )
    max_llm_calls_per_run: int = Field(
        default=25,
        alias="MAX_LLM_CALLS_PER_RUN",
        description="Circuit breaker: raises LLMBudgetExceededError if a run would exceed this many LLM calls.",
    )
    
    fab_bullet_ratio: float = Field(default=0.65)  # min similarity a rewritten CV bullet must keep vs its cited corpus item
    fab_skill_ratio: float = Field(default=0.85)  # min similarity a claimed skill must have vs the corpus's real skill vocabulary
    fab_letter_ratio: float = Field(default=0.55)  # min similarity a cover-letter sentence must have vs corpus/research/job-context text

    tavily_api_key: SecretStr = Field(default=SecretStr(""), alias="TAVILY_API_KEY")

    @property
    def has_opik(self) -> bool:
        return self.opik_enabled and bool(self.opik_api_key.get_secret_value())

    @property
    def has_tavily(self) -> bool:
        return bool(self.tavily_api_key.get_secret_value())

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
