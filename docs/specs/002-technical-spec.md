# Technical spec — parallel execution plan

Status: draft · Branch: `feat/ops-feedback-evidence` · Companion to `001-product-spec.md`

## Thesis

Anthropic's own criteria for when multi-agent work fails are *agents sharing
context* and *many dependencies between agents*, and they note most coding tasks
have fewer parallelisable parts than research. The most common observed failure
is **duplicated or overlapping work**.

So this document's job is not documentation. It is to drive the dependencies
between the three agents to **zero before any of them starts**, by assigning
exclusive file ownership and fixing the interfaces across those boundaries up
front. If this is done properly, integration is mechanical: a handful of import
lines, no merge conflicts, no agent waiting on another.

## The two rules

1. **Agents create new files. The human does the wiring.**
   Anything that must be touched by more than one feature — `main.py`,
   `schema.sql`, `MatchesStep.tsx` — is edited by nobody but me, at integration,
   in a handful of lines.
2. **Agents run in isolated git worktrees.** An out-of-bounds write cannot reach
   the working tree, so rule 1 is enforced by the filesystem rather than by good
   intentions.

---

## File ownership

| Path | A · ops | B · feedback | C · evidence | Wiring |
|---|:---:|:---:|:---:|:---:|
| `src/joblyst/metrics.py` | **new** | | | |
| `src/joblyst/api/metrics_routes.py` | **new** | | | |
| `src/joblyst/tools/search_job.py` | **edit** | | | |
| `scripts/benchmark_sources.py` | **new** | | | |
| `frontend/app/ops/page.tsx` | **new** | | | |
| `migrations/001_source_attempts.sql` | **new** | | | |
| `src/joblyst/api/feedback.py` | | **new** | | |
| `scripts/export_feedback_dataset.py` | | **new** | | |
| `frontend/components/FeedbackButtons.tsx` | | **new** | | |
| `migrations/002_job_feedback.sql` | | **new** | | |
| `src/joblyst/graph/nodes/rank_jobs.py` | | | **edit** | |
| `src/joblyst/schemas/schemas.py` | | | **edit** | |
| `src/joblyst/evidence.py` | | | **new** | |
| `frontend/components/JobEvidence.tsx` | | | **new** | |
| `frontend/utils/api.ts` | | *read* | **edit** | |
| `src/joblyst/api/main.py` | | | | **human** |
| `frontend/components/MatchesStep.tsx` | | | | **human** |
| `schema.sql` | | | | **human** |
| `docs/engineering_log.md` | | | | **human** |

No cell has two owners. `frontend/app/globals.css` is owned by nobody: **new
components use inline styles**, matching the existing codebase, so there is
nothing to collide over.

---

## Interface contracts

Fixed now so the wiring is mechanical and the agents cannot drift.

### A — metrics

```python
# src/joblyst/metrics.py
@dataclass
class SourceAttempt:
    source: str
    outcome: Literal["ok", "empty", "timeout", "error", "skipped"]
    latency_ms: int
    job_count: int
    consumed: bool = False      # set after the cascade decides

def record_search(query: str, attempts: list[SourceAttempt]) -> None: ...
def source_stats(since_hours: int = 168) -> list[dict]: ...
```

`consumed` is unknown while a source is being fetched and known only once the
cascade finishes, so `run_search` collects attempts locally and flushes **once**
at the end, setting `consumed = name in used`. One write per search, not one per
source. Storage follows the `sessions.py` pattern exactly: in-memory when
`db.is_open()` is false.

```python
# src/joblyst/api/metrics_routes.py
router = APIRouter(prefix="/api/metrics", tags=["metrics"])
# GET /api/metrics/sources
```

### B — feedback

```python
# src/joblyst/api/feedback.py
router = APIRouter(prefix="/api", tags=["feedback"])
# POST /api/feedback  body: {thread_id: UUID, job_id: str, verdict: "good"|"bad",
#                            reason: str | None, fit_score: int}
# upsert on (thread_id, job_id)
```

```tsx
// frontend/components/FeedbackButtons.tsx — self-contained, does its own POST,
// imports only API_URL from utils/api.ts (a read, not an edit)
<FeedbackButtons threadId={string} jobId={string} fitScore={number} />
```

### C — evidence

```python
# src/joblyst/schemas/schemas.py
class Evidence(BaseModel):
    claim: str            # e.g. "Airflow"
    job_quote: str        # verbatim from the posting
    profile_quote: str    # verbatim from the profile

# JobScore and RankedJob both gain: evidence: list[Evidence] = Field(default_factory=list)
```

```python
# src/joblyst/evidence.py
def verify(evidence: list[Evidence], job_text: str, profile_text: str) -> tuple[list[Evidence], int]:
    """Drop any item whose quotes are not verbatim spans. Returns (kept, dropped_count)."""
```

```tsx
// frontend/components/JobEvidence.tsx — presentational only
<JobEvidence evidence={Evidence[]} />
```

---

## Agent briefs

Each brief carries the four things a subagent needs: objective, output format,
tool/boundary guidance, and a definition of done.

### Agent A — source operability

- **Objective.** Make every job-source attempt observable, and answer with data whether Jooble is queried on searches that never consume it.
- **Output.** The five files marked A above, plus a one-paragraph summary of what the benchmark measured.
- **Boundaries.** Touch `search_job.py` only inside the `fetch()` closures and the end of `run_search`. Do not change the cascade's thresholds or ordering — this feature observes, it does not fix. Do not touch `main.py`.
- **Done.** `uv run pytest -q` green; `uv run python scripts/benchmark_sources.py --runs 3` writes a markdown table; `GET /api/metrics/sources` returns per-source aggregates when the router is mounted.

### Agent B — feedback loop

- **Objective.** Capture good/bad verdicts with reasons and export them as an offline eval dataset. Change no ranking behaviour.
- **Output.** The four files marked B above.
- **Boundaries.** The component must be self-contained and must not edit `MatchesStep.tsx`, `main.py`, `utils/api.ts`, or `globals.css`. Follow the storage pattern in `api/sessions.py` including the in-memory fallback.
- **Done.** Round-trip test passes: POST a vote → read it back → export produces JSONL matching the existing ranking-dataset field names.

### Agent C — evidence-linked scoring

- **Objective.** Every matched skill carries a verbatim quote from the posting and from the profile, with a deterministic verifier that drops unverifiable quotes.
- **Output.** The four files marked C above, plus the new `rank_jobs` prompt text as a **proposal in the summary** — do not push it to Opik.
- **Boundaries.** Prompts live in Opik; you may read them via `joblyst.prompts` but must not call `create_prompt`. I will push the prompt and re-run the eval myself.
- **Done.** `verify()` has unit tests covering verbatim match, near-miss, and whitespace-normalised match; existing 36 tests still pass.

---

## Integration (human, ~15 min)

1. `main.py`: two `app.include_router(...)` lines.
2. `MatchesStep.tsx`: `<FeedbackButtons .../>` and `<JobEvidence .../>` inside the existing `<article className="job">`.
3. `schema.sql`: append both migrations.
4. Push C's proposed `rank_jobs` prompt to Opik as a new version.
5. `uv run ruff check src tests scripts && uv run pytest -q`
6. `cd frontend && npm run build`
7. `docker build -t joblyst-api .`
8. `uv run python -m evals.run_evals --suite ranking --yes` → **must be ≥ 0.87**.
9. Engineering-log entry: symptom → cause → fix → measured result, per feature.

## Rollback

Each feature is one agent, one worktree, one commit. If the ranking eval comes
back under 0.87, revert C's commit and keep A and B — the ownership split means
that is a clean revert, not an untangling.

## Risks accepted

- **C can regress ranking.** Gated by step 8, with a numeric floor decided in advance so the decision is not made under pressure.
- **A's instrumentation adds a write to every search.** One batched insert at the end of `run_search`, not per source; failures in `record_search` must never fail a search.
- **Jooble quota.** The benchmark script runs live searches. Cap `--runs` at 3 and prefer the cache path while developing — the lifetime quota is 500.
