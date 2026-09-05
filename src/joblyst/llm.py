"""Chat-model factory."""

from __future__ import annotations

import os
from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from joblyst.config import get_settings


def _export_openai_key() -> None:
    """pydantic-settings reads .env but does not export to os.environ, which is
    where the OpenAI client looks for its key."""
    if os.environ.get("OPENAI_API_KEY"):
        return
    key = get_settings().openai_api_key.get_secret_value()
    if key:
        os.environ["OPENAI_API_KEY"] = key


@lru_cache(maxsize=8)
def get_chat_model(model: str = "openai:gpt-4o-mini", temperature: float = 0.0) -> BaseChatModel:
    """Return a cached chat model for a LangChain provider string."""
    if model.startswith("openai:"):
        _export_openai_key()
    return init_chat_model(model, temperature=temperature)
