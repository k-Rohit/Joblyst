# Joblyst

A job-matching agent, built by studying [jamwithai/observable-job-agent](https://github.com/jamwithai/observable-job-agent).

## Setup

```bash
uv sync --all-groups
cp .env.example .env    # fill in OPENAI_API_KEY, optionally OPIK_API_KEY
uv run python scripts/check_setup.py
```
