"""Sanity check: one traced LLM call. Confirms OPENAI_API_KEY and the Opik keys
(if set) actually work before any agent code is written.

Usage: uv run python scripts/check_setup.py
"""

from __future__ import annotations

import sys

from joblyst.config import get_settings
from joblyst.llm import get_chat_model
from joblyst.tracing import get_tracer


def main() -> int:
    settings = get_settings()

    if not settings.openai_api_key.get_secret_value():
        print("OPENAI_API_KEY is empty. Copy .env.example to .env and fill it in.")
        return 1

    tracer = get_tracer(thread_id="check-setup", tags=["setup-check"])
    print(f"Opik tracing: {'ON — ' + settings.opik_project_name if tracer else 'OFF'}")

    model = get_chat_model("openai:gpt-4o-mini")
    config = {"callbacks": [tracer]} if tracer else {}
    response = model.invoke("Reply with exactly: setup ok", config=config) # type: ignore

    print(f"Model replied: {response.content!r}")
    if tracer:
        tracer.flush()
        print("Check your Opik project dashboard for the trace.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
