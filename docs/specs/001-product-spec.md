# Product spec — Operability, feedback, and evidence

Status: draft · Branch: `feat/ops-feedback-evidence` · Owner: Kumar Rohit

## Why now

Joblyst is measured offline (ranking 0.891, extraction 0.738, fabrication 0.104) but it is
not **operated**. Three gaps, in order of how much they hurt:

1. We cannot see what the live system is doing per job source.
2. We have no signal from users about whether a match was actually good.
3. A fit score is an assertion. Nothing points at the text that justifies it.

Each gap is independent of the others. That is deliberate — it is what makes them
safe to build in parallel (see the technical spec).

---

## Feature A — Source operability

### Problem

`run_search` queries five live sources plus an offline snapshot. Every source
swallows its own failures:

```python
except Exception:  # noqa: BLE001 - a dead source is an empty source
    return []
```

Four different outcomes are currently indistinguishable — all of them end as
"this source is absent from `sources_used`":

| Real outcome | What we can observe today |
|---|---|
| No API key, never queried | absent |
| Queried, raised an error | absent |
| Queried, hit the soft deadline | absent |
| Queried fine, genuinely zero results | absent |

So "Adzuna returned nothing today" and "Adzuna has been broken for a week" look
identical, and the fallback to `cached_jobs.json` has never been counted.

### Suspected defect, to be confirmed by this feature

In concurrent mode (`SCOUT_CONCURRENT_SOURCES`, default **on**) every available
source is submitted to the thread pool up front:

```python
futures = {name: pool.submit(...) for name, fn in fetchers.items()}
```

The cascade's `if len(jobs) < 5` gates then decide only whether to **consume** a
result — not whether to **make the request**. Jooble is in that dictionary, and
Jooble's key carries a **500-request lifetime quota**, with a code comment
stating it should "only spend it when the other sources genuinely came up short."

Reading the code, that comment appears to be false whenever concurrency is on.
Feature A must make this visible as data, not as an argument. If confirmed, the
fix is a separate change — this feature's job is to surface it.

### Done when

- Every source attempt records: `source`, `outcome` ∈ {`ok`, `empty`, `timeout`, `error`, `skipped`}, `latency_ms`, `job_count`, and `consumed` (did the cascade use it).
- Attempts persist to Postgres, with the in-memory fallback used elsewhere when `DATABASE_URL` is unset.
- `GET /api/metrics/sources` returns, per source: attempts, success rate, error rate, timeout rate, **consumed rate**, p50/p95 latency, and overall cache-fallback rate.
- `/ops` renders that as a table, no auth, read-only.
- `scripts/benchmark_sources.py --runs N` executes N searches and writes a dated markdown table to `reports/`.
- **Acceptance:** the benchmark output answers "is Jooble queried on searches that never consume it?" with a number.

### Out of scope

Grafana, alerting, per-user attribution, retention policy, historical backfill.

---

## Feature B — User feedback as an offline dataset

### Problem

Ranking quality rests on 46 items labelled by one person. There is no mechanism
for the system to accumulate judgement from real use, and no way to tell whether
a 72 that a user rejected differs systematically from a 72 they liked.

### Explicitly not

This is **not** online learning, and nothing in this feature changes ranking
behaviour at runtime. Feedback is collected, stored, and exported for offline
reranking evaluation. Any model or prompt change based on it is a later,
separately measured decision. Self-training on unvalidated user clicks would
make quality unfalsifiable, which is the opposite of what this project is for.

### Done when

- Each job card carries a good-match / bad-match control plus an optional reason: wrong seniority · wrong domain · wrong location · already applied · other (free text, 200 chars).
- A vote stores enough to reconstruct an eval item later: `thread_id`, `job_id`, `fit_score` at vote time, verdict, reason, timestamp.
- `POST /api/feedback` is idempotent per `(thread_id, job_id)` — a re-vote updates.
- `scripts/export_feedback_dataset.py` emits JSONL in the same shape as the existing ranking dataset, so it can be loaded as an Opik dataset without transformation.
- **Acceptance:** vote in the browser → row in the database → export produces a file the existing eval loader accepts.

### Out of scope

Auth, per-user history, feedback on tailored output, any retraining.

---

## Feature C — Evidence-linked scoring

### Problem

`RankedJob` carries `fit_score`, `fit_explanation` (prose), `matched_skills` and
`gaps`. None of it is traceable. A `matched_skills: ["Airflow"]` does not say
where in the posting Airflow was required, nor where in the profile it was
evidenced — the same ungrounded-claim problem the tailoring path already solved
with `corpus_ref` citations and a fabrication judge.

The ranking eval already measures one half of this (`SkillsInProfile`, 0.978 —
is the skill really in the profile). It does not check the other half: is the
skill really required by the job.

### Done when

- `JobScore` and `RankedJob` carry `evidence: list[Evidence]`, where `Evidence` is `{claim, job_quote, profile_quote}`.
- The `rank_jobs` prompt in Opik requires both quotes to be **verbatim** spans of the inputs it was given.
- A deterministic post-check drops any quote not found verbatim in its source text and counts the drops — the model is not trusted to self-certify.
- The frontend shows evidence beneath each matched skill.
- **Acceptance (hard gate):** the ranking eval stays at or above **0.87** (0.891 baseline minus the ±0.02 run-to-run noise measured earlier). Below that, the change is reverted, not argued with.
- **Acceptance (reported):** the share of evidence quotes that verify verbatim.

### Out of scope

Evidence for `gaps`, changing the fit-score scale, re-ranking on evidence count.

---

## What this session is *not* trying to prove

That three agents are faster than one. The point is that three independent
features with zero shared write-surface can run concurrently **because the spec
made them independent** — and that the integration afterwards is mechanical
rather than a merge fight.
