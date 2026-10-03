# Engineering log

A running record of problems found in Joblyst, what was changed, and what
measurably improved. Each entry is written to be understood without reading the
code first.

Format for every entry:

- **Symptom** — what went wrong, in plain terms
- **Root cause** — the actual reason, with the file and line
- **Fix** — what changed
- **Result** — the measured before/after

---

## 2026-09-18 · Real skills reported as fabricated (short skill names)

**Symptom.** A candidate whose CV clearly listed `Go` and `R` had both flagged
by the fabrication validator as skills they had invented.

**Root cause.** `corpus.py` builds the list of "skills this person really has"
by reading the CV. It discarded any entry shorter than three characters:

```python
if len(text) < 3:
    return
```

So `Go`, `R`, `C` and `C#` never entered the corpus. The tailored CV then
claimed a skill the corpus had no record of, and the validator — correctly, on
the data it was given — called it fabricated.

**Fix.** Skills now have a lower length floor than other content. A
two-character skill is real; a two-character *bullet* is a parsing artifact, so
only skills were exempted.

**Result.** On a CV listing `Python, Go, R, C#, SQL, Rust`:

| | before | after |
|---|---|---|
| skills found in CV | 3 of 6 | **6 of 6** |
| real skills wrongly flagged as fake | 2 | **0** |

---

## 2026-09-18 · A CV listing skills one per line lost all of them

**Symptom.** One fixture CV parsed **zero** skills, even though it had a normal
`SKILLS` section. Its skills were listed one per line rather than comma-separated.

**Root cause.** `corpus.py` decides where sections start by spotting headings,
and treated *any* short all-caps line as one:

```python
if line.isupper():
    return True
```

The first skill in the list was `SQL` — all caps. It was read as a new section
heading, which ended the skills section. Everything after it became work
experience.

**Fix.** A lone all-caps token of four characters or fewer is now treated as a
skill, not a heading. Real one-word headings (`EDUCATION`, `CERTIFICATIONS`) are
longer, so they still work, as do multi-word ones like `TECH STACK`.

**Result.** That CV went from **0 skills and 25 bullets** to **10 skills and 17
bullets**. Any CV listing `SQL`, `AWS`, `ETL` or `GCP` on its own line was
affected.

---

## 2026-09-18 · Two separate skills merged into one

**Symptom.** After the fix above, a CV showed a single skill called
`Python dbt` — two real skills glued together.

**Root cause.** PDFs wrap long lines, so `corpus.py` rejoins a line with the
previous one when the previous line looks unfinished. `Python` followed by
`dbt` matched that rule, since `dbt` is lowercase.

**Fix.** Two lone words on consecutive lines are now treated as a list, not a
wrapped sentence. Genuinely wrapped bullets still rejoin, because those start
from a line with several words.

**Result.** `Python dbt` became `Python` and `dbt`. Wrapped bullets verified
intact — a bullet split across two PDF lines still reassembles into one item.

---

## 2026-09-18 · The fabrication checker flagged every skill on some CVs

**Symptom.** On a CV whose skills heading read `TECHNICAL PROFICIENCIES`, the
validator flagged **every single skill** as fabricated, on an entirely honest CV.

**Root cause.** There were two copies of the deterministic checking logic — one
in `validation.py`, one written separately inside `validation_hybrid.py` — and
only the second one runs in the app. The copies had drifted. The live one was
missing a safety net: when no skills section could be parsed, the good copy
falls back to searching the whole CV text, while the live copy just scored every
skill `0.00` and flagged it.

The comment above that code claimed it was `unchanged from validate_pack`. It
was not.

**Fix.** The skill check was extracted into one shared function that both
validators call, so the deterministic answer cannot differ between them.

**Result.** On the same CV and the same generated content:

| | before | after |
|---|---|---|
| real skills flagged as fake | 3 of 3 | **0 of 3** |

---

## 2026-09-18 · Fabrication checker restructured into two clear stages

**Symptom.** The checker's behaviour was hard to reason about: the LLM was
called for every claim that passed the cheap check, including skills, where
there is no judgment to make. Roughly 20 sequential LLM calls per CV.

**Root cause.** Design, not a bug. No rule said which content deserved an LLM
opinion, so everything got one.

**Fix.** An explicit two-stage rule:

| content | cheap deterministic check | LLM check |
|---|---|---|
| experience & project bullets | yes | yes, if the cheap check passes |
| summary | yes | yes, if the cheap check passes |
| cover letter | yes | yes, if the cheap check passes |
| skills | yes | **never** — a skill is a lookup, not a judgment |
| headline | yes | **never** — too short to hide a changed detail |

The LLM calls now run concurrently rather than one after another. The design is
*union-only*: the LLM can only **add** findings, never overturn one the
deterministic check made — so an unpredictable component can never silently
clear something a reproducible check caught.

**Result.** Verified end to end: a CV bullet where `2M events` had been changed
to `8M events` was caught, with the reason *"The number of events per day was
changed from 2M to 8M"*. That edit is a single character, so the cheap
similarity check scores it 0.98 and is structurally blind to it. An honestly
reworded bullet in the same run was correctly left alone. Whole CV checked in
2.2 seconds.

---

## 2026-09-18 · The headline and summary were never checked at all

**Symptom.** The two most prominent lines on a tailored CV — the headline and
the professional summary — were generated by the model and never validated.

**Root cause.** The schema *requires* both fields, so the model must write them
on every run. But no prompt instruction described them, nothing tied them back
to the real CV (unlike bullets, which must cite a source line), and the
validator's loops skipped them entirely.

So the headline could claim `Senior Data Engineer, 8 years' experience` with
nothing to stop it.

**Fix.** Both are now validated: grounded by searching the whole CV, since a
summary legitimately draws on several parts of it at once. The summary also gets
the LLM check; the headline does not.

**Result.** The one place where the project's "never fabricated" guarantee did
not actually hold is now covered.

---

## 2026-09-18 · The fabrication judge flagged honest rewrites

**Symptom.** A perfectly accurate summary was flagged, with the judge
complaining it *"omits the detail about building an ingestion service"*.

**Root cause.** The prompt asked whether details in the rewrite appear in the
source, but the model also checked the reverse — whether everything in the
source appears in the rewrite. Leaving things out is normal and fine when
tailoring a CV; it is not fabrication.

**Fix.** The prompt now states explicitly that omission is never a problem, and
that only added or altered details count.

**Result.** The false flag disappeared. The real `2M → 8M` fabrication in the
same test was still caught.

---

## 2026-09-18 · Generated test CVs rendered as mostly blank pages

**Symptom.** The synthetic CVs built for evaluation looked broken — text drifting
off to the right, large empty gaps, bullets cut off.

**Root cause.** The PDF library's `multi_cell` leaves the cursor at the *right
edge of the same line* by default, so each line started where the last one
ended instead of on a new line.

**Fix.** Forced a newline at the left margin after every line.

**Result.** All five CVs render as normal resumes. Text extraction was never
affected — only the visual layout — which is why the parsing numbers were the
same before and after.

---

## 2026-09-18 · The offline job cache never ran, and could only return one job

**Symptom.** Joblyst has a `CacheSource` — a local snapshot of job postings meant
to serve as a fallback when the live job APIs return nothing. It never produced
a single result.

**Root cause.** Two independent faults.

1. **It was never called.** `run_search` builds its list of sources from
   JSearch, Adzuna, Remotive, Himalayas and Jooble. `cache` was never added to
   that list, so the fully-written class sat unused — the same fault Himalayas
   and Jooble had earlier in this project.
2. **It returned after the first match.** Inside `fetch`, the sort and the
   `return` were indented into the loop body, so the function exited as soon as
   it found one matching posting instead of ranking all of them.

**Fix.** Wired the cache in as the final step of the search cascade, running
only when the live sources come up short. It reads a local file rather than the
network, so it stays out of the thread pool. Also dedented the sort and return
so the whole snapshot is ranked.

**Result.** On a 5-posting snapshot searched for "data engineer":

| | before | after |
|---|---|---|
| jobs returned by `CacheSource.fetch` | 1 | **4** |
| jobs when every live source is down | 0 | **4** (`sources_used=['cache']`) |

The irrelevant posting (a frontend role) was correctly excluded, so the ranking
still works — it just no longer stops at the first hit.

**Why it matters for evaluation.** The baseline batch runs each CV many times.
Without a cache every run hits the live APIs, and Jooble's quota is 500 requests
for the lifetime of the account. The cache makes repeated eval runs affordable,
and makes them reproducible — the same job pool every time, so a score change
reflects a prompt change rather than a job board's mood.

---

## 2026-09-18 · Snapshot builder only captured one query's results

**Symptom.** `scripts/create_snapshpt.py` was written to loop over 11 job-title
queries per source, but the very first test run would have produced a cache
dominated by a single query, or crashed outright depending on which source ran
first.

**Root cause.** Two copies of the same mistake:

1. Adzuna's `jobs.extend(adzuna_jobs)` was indented one level too far out — after
   the `for q in QUERIES` loop instead of inside it — so only the last query's
   results (`"Gen AI Engineer"`) were ever kept; the other 10 were fetched and
   discarded.
2. Remotive and Himalayas were never put in their own loop at all. Both reused
   the leftover `q` variable from the Adzuna loop above, so they only ever
   searched that same last query — and if Adzuna had no key configured, `q` was
   never assigned, so the script crashed with `NameError`.

A third, smaller issue: the dedup step computed a clean list but the write step
saved the raw, duplicate-containing one instead.

**Fix.** Moved `.extend()` inside the loop for Adzuna, gave Remotive and
Himalayas their own `for q in QUERIES` loops, and pointed the file write at the
deduplicated list.

**Result.** The committed snapshot (`data/cached_jobs.json`) has 99 postings
spanning most of the query list — Data Scientist, Senior Data Engineer, ML
Engineer, Data Analyst, Business Analyst, Analytics Engineer, AI Engineer — with
zero duplicate (title, company) pairs. Confirmed `CacheSource` reads real,
varied jobs back from the file rather than the file just existing.

**Known gap:** all 99 postings are India-only (`country="in"`), and there are
no "hardware engineer" postings — meaning the domain-mismatch hard case planned
for the baseline batch has nothing realistic to fall back on if its live search
ever fails.

---

## 2026-09-19 · Fixture CVs were built for the wrong country

**Symptom.** Only 1 of 5 fixture CVs was actually India-based. The other four
had candidates in San Francisco, London, Berlin and Austin.

**Root cause.** The fixture composition was carried over from the reference
repo's international spread without checking it against Joblyst's own scope.
Joblyst is India-only end to end — `DEFAULT_COUNTRY = "in"` in `search_job.py`,
the Jooble base URL pinned to `in.jooble.org`, and `cached_jobs.json` built
`country="in"` only — so a fixture candidate targeting London or Austin
exercises a search path the real app never runs.

**Fix.** Regenerated all 5 CVs with India-based locations and names, keeping
every structural property that was the actual point of having 5 different
CVs unchanged — same seniority spread, same heading styles, same skill
formatting, same wrapped-bullet stress cases:

| file | was | now |
|---|---|---|
| `junior_ds_us` → `junior_ds_in` | San Francisco | Bengaluru |
| `senior_mle_uk` → `senior_mle_in` | London | Hyderabad |
| `career_changer_in` | Bengaluru | unchanged |
| `lead_de_remote` → `lead_in_remote` | Berlin | Pune, remote-ok |
| `mid_analyst_us` → `mid_analyst_in` | Austin | Gurugram |

**Result.** Verified the relocation changed nothing structural — corpus item
counts and parsed-skill counts are identical before and after across all 5
CVs, confirming the swap only touched location/name text, not the layout
properties the fixtures exist to test. `cached_jobs.json` (already India-only)
now country-matches every persona instead of just one.

---

## 2026-09-19 · fetch_jobs silently discarded a second tool call

**Symptom.** Inspecting a real trace of a search on my own resume, the LLM
issued **two** `search_jobs` tool calls for a reformulated query — one for
on-site roles, one for remote — but the ranked results only ever reflected
one of them. The dropped call left no trace anywhere: not in the errors list,
not in the UI, not in `reports/baseline.json`.

**Root cause.** `fetch_jobs.py` read `message.tool_calls[0]` unconditionally.
The system prompt asks the model to call the tool exactly once, but a prompt
is a request, not a guarantee — the same reasoning already applied to
`MAX_QUERY_WORDS` in this same file, just not to this line.

**Fix.** Loop over every tool call the LLM issues instead of hardcoding index
`0`. Each call runs its own search; the results are deduplicated and merged
together (reusing the existing `_dedupe_with_existing` helper), and the
sources lists are merged too. When more than one tool call happens, it's now
logged as a visible `errors` entry instead of disappearing.

**Result.** Verified all three paths with mocked LLM responses:

| scenario | before | after |
|---|---|---|
| 1 tool call (normal) | 1 search run | 1 search run — unchanged |
| 0 tool calls | 1 fallback search, logged | 1 fallback search, logged — unchanged |
| 2 tool calls | **1 search run, 1 silently dropped** | **2 searches run, merged, logged** |

---

## 2026-09-19 · Ranking never saw the candidate's profile on a normal search

**Symptom.** A dataset item pulled from a real run showed a Senior Data
Scientist posting requiring "4+ years of commercial experience" scored `85`
against a candidate with 1.5 years — a gap the ranking prompt has an explicit
rule against ("do not claim a skill... name it as a gap instead"), yet the
explanation read like a coin flip: "particularly with their experience in
data science... the candidate's specific years of experience were not
provided."

**Root cause.** `_render_profile` in `rank_jobs.py`:

```python
def _render_profile(profile, target_role=None):
    base = (f"Name: ...\nYears experience: {profile.years_experience}\n...")
    if target_role:
        base += "\nNote: candidate is deliberately targeting..."
        return base
    return ""
```

`return base` sat inside the `if target_role:` branch. Every normal search —
the vast majority of runs, since `target_role` is only set for a deliberate
domain pivot — hit `return ""` instead, sending the ranking LLM a prompt
reading `"Candidate profile:\n\n"` with nothing after it. The model had no
seniority, no skills, no years of experience, nothing — every fit score and
explanation for a plain search was generated with **zero real information
about the candidate**. This wasn't a copy from the reference repo's own
`_render_profile` (confirmed by reading it directly — theirs has no `if`, no
early return, no `target_role` concept at all): it was introduced when
`target_role` was added to this project and the return statement got nested
one level too far, the same shape of bug as the earlier indentation-cascade
issues in `validation_batch_hybrid.py` and `create_snapshpt.py`.

**Fix.** Moved `return base` outside the `if`; dropped `return ""` entirely.
The `target_role` branch now only appends a note to the same profile text
instead of gating whether the profile is sent at all.

**Result.** Verified both paths directly:

| call | before | after |
|---|---|---|
| `_render_profile(profile)` | `""` (empty) | full profile: name, seniority, skills, years experience, locations |
| `_render_profile(profile, target_role="AI Engineer")` | full profile + note | unchanged — full profile + note |

Every fit score and explanation ever produced by a normal (non-`target_role`)
search before this fix was generated with no real candidate data — the
domain-mismatch rule, the no-fabrication rule, all of `RANK_JOBS_PROMPT`'s
guardrails had nothing to check against. This is the largest-impact bug found
in the project so far; any prior baseline numbers or eval dataset items built
before this fix should be treated as invalid and rebuilt.

**Follow-up hardening.** The root problem behind this bug wasn't "input was
missing" — the profile was always present, a control-flow bug just threw it
away before it reached the LLM. The general lesson: an LLM never refuses when
context is missing, it answers anyway and invents whatever's needed to sound
plausible, so a hollow prompt is worse than a crash, not better. Required
prompt inputs should fail loud, not degrade quietly; only genuinely optional
context (`target_role`, `research_notes`) should be allowed to be absent.
Added two guards to `rank_jobs()` so this exact failure mode can't ship
silently again:

```python
assert profile is not None, "rank_jobs requires profile to already be set"
...
rendered_profile = _render_profile(profile, state.get("target_role"))
assert rendered_profile, "rank_jobs: profile rendered empty — refusing to rank blind"
```

Verified the second assertion actually fires: patched `_render_profile` to
return `""` (reproducing the exact old bug) and confirmed `rank_jobs` now
raises immediately instead of sending the empty prompt to the LLM. Also moved
the profile render outside the per-batch closure — previously re-rendered
once per batch for no reason, now rendered once and reused.

---

## 2026-09-19 · Ranking had no explicit rule for experience-level gaps

**Symptom.** A Senior Data Scientist posting requiring "4+ years" scored 85
for a candidate with 1.5 years. Most of that was the empty-profile bug above,
but even with the profile visible, `RANK_JOBS_PROMPT` never said what to do
about an experience gap, so how hard the model penalized it was left to chance.

**Fix.** Added one rule to `RANK_JOBS_PROMPT`: when a posting states a minimum
years of experience well above the candidate's, that is a hard gap and scores
below 60 (the good-fit threshold), however well the skills match.

**Result.** Live test, same 3 postings, 3 identical runs, candidate at 1.5 years:

| posting | needs | score |
|---|---|---|
| Senior Data Engineer | 6+ years | **20** |
| Data Engineer | 1-3 years | **85** |
| Data Engineer | 3+ years | **60** |

The big gap is pushed far below the threshold, the matching role is untouched,
and results were identical across runs. The small gap (1.5 vs 3+ years) lands
exactly on the threshold, so "well above" is still a judgment call for
borderline gaps.

---

## 2026-09-19 · Prompt changes were not versioned, so improvements could not be traced

**Symptom.** The ranking prompt had been edited twice (a no-fabrication rule, then an experience-gap rule) and scores got better each time. But nothing recorded which prompt text produced which traces or eval scores. The only history was in git, and Opik had no link to it.

**Root cause.** Prompts were plain Python strings. Opik's Prompt Library was never used, so it had no idea the text existed or that it changed.

**Fix.** Added `register_prompts()` in `tracing.py`. It sends all five prompts to Opik's library under stable names. Unchanged text is a no-op; changed text becomes a new version. It runs at Streamlit startup and at the start of `run_batch.py --yes`. A failure is logged, never raised, so prompt sync cannot block a run.

**Result.** All five prompts now exist in Opik with version 1 (verified with `get_prompt_history`). From here, every prompt edit creates a new version automatically. The fabrication judge prompt (`drift_check`, moved from `validation_hybrid.py` into `prompts/`) is registered too, since its wording decides what counts as a flag. Earlier rank_jobs versions were not backfilled, so its history starts at the current text. Next step: attach the prompt version to eval experiments so a score change can be tied to a prompt change.

## 2026-09-21 · Ranking eval replay left out `target_role`, so pivot items looked like regressions

**Symptom.** The first full ranking eval over the 46 labeled items scored `score_on_right_side` 0.870 (40 of 46). Three of the six misses were Kumar's AI-role jobs, which all scored 15-40 points lower on replay than in the original run (for example 70 to 55, 80 to 40).

**Root cause.** The original `ai_engineer_pivot` run passed `target_role = "AI Engineer"`, and the ranker adds a note to the profile for it ("weigh skills/projects over past job titles"). The dataset items never stored `target_role`, so the replay ranked those jobs for a plain Data Engineer. The eval asked a different question than the one the labels were made for. `target_role` lives on the trace input, not the output the builder read.

**Fix.** `build_eval_dataset.py` now stores `target_role` (read from the trace input) in every ranking item, the 46 existing items were backfilled in place (ids and labels unchanged, checked), and the eval task passes it into `rank_jobs`.

**Result.** Rerun: 0.891 (41 of 46). The AI-role misses from the missing note are gone. Measured run-to-run randomness on the 39 non-pivot items: 36 identical scores, max difference 10 points, 1 item changing side of 60 (Honeywell, 55 to 65). The larger gap that remains is replay versus the original scores (mean 7.5 points, 8 items off by 15 or more), because the originals were scored 4 jobs per prompt and the replay scores one job per call. Still open: the job's `remote` flag is not stored either, so the replay always sends `remote=False` (12 of the 46 originals were remote).

## 2026-09-24 · Profile extraction had never been measured; first run scored 0.57

**Symptom.** `extract_profile` runs on every search, but nothing checked its output. Bugs in it were invisible: a wrong `primary_roles` silently becomes the job-search query (`fetch_jobs.py` uses `" ".join(profile.primary_roles[:2])` when the LLM supplies no query), so a bad extraction quietly searches for the wrong jobs.

**Root cause.** No eval existed. `data/labels/expected_profiles.yaml` had 5 hand-verified entries sitting unused since Phase 1.

**Fix.** Added `scripts/build_extraction_dataset.py` (yaml + fixture CV text -> Opik dataset `joblyst-extraction-cases`, verified entries only) and a `ProfileFieldAccuracy` metric in `evals/metrics.py`, wired as `--suite extraction` in `evals/run_evals.py`. Scoring is deterministic, no judge: exact match for `seniority`/`remote_ok`, 0.5-year tolerance for `years_experience`, and set F1 for the list fields. `projects` is deliberately not scored (free text, and its known bug is tracked separately).

**Result.** First run: **0.569** mean field accuracy over 5 CVs. Per field: skills 0.983, locations 0.647, remote_ok 0.600, seniority 0.600, years_experience 0.600, primary_roles 0.550, languages **0.000**. Six real defects surfaced on the first run, none of which anything had caught before:
- `languages` comes back `[]` on all 5 CVs. The prompt says only "spoken languages" and gives no rule for a CV that does not state one explicitly.
- `career_changer_in`: expected `seniority: junior` / `years_experience: None` (11 years of *teaching*, ~0 in data), got `mid` / `11.0` — teaching years counted as data experience.
- `senior_mle_in`: `seniority` expected senior, got lead (off by one rung).
- `remote_ok` wrong on 2 of 5, including a CV that says "Open to hybrid".
- `locations` lists every city in the CV (past offices included) instead of where the candidate can work.
- `primary_roles` transcribed job history verbatim, including `undergraduate research assistant`.

Worth noting: the reference repo wrote this same suite but never ran it — its labels were left `verified: false`, so its report has no number here.

## 2026-09-24 · primary_roles was transcribing job history instead of searchable roles

**Symptom.** `primary_roles` scored 0.550. On `junior_ds_in` it returned `['junior data scientist', 'data science intern', 'undergraduate research assistant']` where the label is `['data scientist']`. Since `primary_roles[:2]` becomes the fallback search query, that output makes the agent search for internships.

**Root cause.** One self-contradicting line in the prompt: "the job titles/roles this person is a fit for" (forward-looking) "ordered with their current or most recent role first" (backward-looking). The model resolved the contradiction by listing employment history, and only scored well when a candidate's past titles happened to equal their target roles.

**Fix.** Rewrote the `primary_roles` instruction to state what the field is *for* (search queries, so clean searchable names), to ground roles in responsibilities rather than titles (a "Mathematics Teacher" doing Power BI and predictive models yields "data analyst"), to keep the level reached and add the natural next step, and to exclude outgrown roles (internships, student positions) and off-domain jobs.

**Result.** `primary_roles` 0.550 -> **0.620**, overall 0.569 -> 0.588. Mixed, not a clean win: 3 CVs improved, 2 regressed. The "never list outgrown roles" clause worked everywhere it applied (`junior_ds_in` 0.00 -> 1.00, dropping the intern and research-assistant entries). The "include the natural next step" clause backfired — the model *replaces* held roles with invented ones rather than adding: `senior_mle_in` went 1.00 -> 0.40 (dropped `senior machine learning engineer` and `data scientist`, invented `ml platform lead`) and `lead_in_remote` 0.75 -> 0.50 (dropped the held `senior data engineer`, invented `data architect`). Still open: make next-step roles explicitly additive. With only 5 CVs each one moves the mean by 20%, so this number is directional at best.

## 2026-09-26 · A trimmed query left a dangling "OR" and matched no job at all

**Symptom.** In a `baseline-batch` trace the search query was `'Data Analyst OR Business Analyst OR'`. No posting is titled that, so the search came back nearly empty: 10 jobs, remotive only, adzuna contributed nothing. The only sign of trouble was an `errors` entry saying the query had been trimmed.

**Root cause.** Two independent bugs feeding the same path.
1. `_trim_query` cut by word count alone. The LLM returned `'Data Analyst OR Business Analyst OR Analytics Intern'` (7 words), the limit is 6, so it kept the first 6 words and left the trailing `OR`. Truncating a list mid-expression produced a query worse than either the original or a clean cut.
2. `_fallback_query` (then inline as `" ".join(profile.primary_roles[:2])`) concatenated two roles into `'data analyst business analyst'` — the same unsearchable shape, reached whenever the LLM supplied no query.

Underneath both: the prompt forbade appending skills but never forbade a *list* of roles, and boards match a query against one job title literally.

**Fix.** `_trim_query` now splits on list separators (standalone `or`/`and`, comma, semicolon, pipe) **before** the word cut and keeps the first segment; slash and ampersand are deliberately not separators, since `AI/ML engineer` and `R&D engineer` are real titles. `_fallback_query` takes `primary_roles[0]`, not two joined. The system prompt states the one-role rule with a worked bad example. The error message no longer claims "trimmed to 6 words", which was untrue for the list case.

**Result.** Re-ran the real `fetch_jobs` LLM call over all 6 fixture profiles plus the AI-Engineer pivot case: **every query came back clean, 0 needed trimming**. `'Data Analyst OR Business Analyst OR Analytics Intern'` now yields `'Data Analyst'`. Verified the separator set leaves `AI/ML engineer`, `R&D engineer` and `lead data engineer` untouched.

Accepted tradeoff: a title legitimately containing "and" gets split (`'machine learning and data engineer'` -> `'machine learning'`). Rare, and the kept half still searches sensibly.

**What the fix surfaced, left unfixed by decision.** The model stopped packing roles into one `OR` query and started splitting them across separate tool calls — 2 or 3 instead of the 1 the prompt asks for, in 6 of 7 cases, stable across 5 runs at temperature 0. The multi-tool-call handling merges them correctly, so this works, but: fan-out is uncapped while `MERGED_CEILING=25` and `joblyst_max_jobs=10` mean a 3rd call's jobs are largely truncated; identical `(query, country, remote)` tuples are not deduped (`career_changer` fires `'data analyst'` twice); one pivot-case call chose `country='gb'` for a Pune candidate; and `ensure_budget` counts only the 1 LLM call, not the N search requests it authorises — which matters because Jooble's quota is 500 requests for the lifetime of the key.

## 2026-10-02 · The extractor counted 11 years of teaching as 11 years of data work

**Symptom.** The extraction eval scored `career_changer_in.pdf` 0.00 on two fields: `years_experience` expected `None`, got `11.0`; `seniority` expected `junior`, got `mid`. Her CV opens "Secondary school mathematics teacher of 11 years moving into data analytics ... Seeking an entry level analyst role".

**Root cause.** The prompt asked for "total years of professional experience", which is literally what the model gave — 11 years of professional teaching. The field is *consumed* as relevant experience but was *documented* as total experience.

**Why it mattered more than a wrong field.** `years_experience` feeds the ranking prompt's experience-gap rule ("when a posting states a minimum years of experience well above the candidate's Years experience, that is a hard gap, score below 60"). Fed `11`, the rule inverts: it starts *confirming* that senior postings fit. The real consequence is in the ranking dataset — Business Data Analyst at VOLTO Consulting, a posting requiring "8-12 Years", scored **60** for her with the explanation "the role requires 8-12 years of experience, which is at the upper limit of her experience". 60 clears `GOOD_FIT_THRESHOLD`, so that job would have been recommended. It is one of the 6 items the human labelled `No` in the ranking review. One extraction bug, surfacing as a failure in two separate evals — and the ranking eval could not have diagnosed it, because scoring an 11-year candidate against an 8-12 year role at 60 is correct reasoning on bad input.

**Fix.** Rewrote the field as "years of PAID professional experience in the field this CV positions them for", with three worked examples. Self-teaching, courses, bootcamps and personal projects are explicitly excluded, as are years in an unrelated profession. Durations are used in the examples rather than date ranges, so the examples cannot go stale.

**Result.** `11.0` -> `2.0`. **By the metric this is a regression** (overall 0.697 -> 0.656) because the label expects `None` and both numbers score 0.00 — and `remote_ok` flipped on one CV at the same time, for reasons I could not pin down. It was kept anyway, deliberately: the metric is binary, so it cannot see that the downstream harm is largely gone. At `2.0` the VOLTO "8-12 years" posting now reads as a genuine gap instead of a satisfied requirement.

Still open, and probably a label question rather than a prompt one: two different models (gpt-4o-mini and gpt-5-mini) and three prompt versions all independently answer `2.0`, reading "self taught ... over the past two years" as two years of experience. `None` is defensible (no *paid* data work) but so is `2.0`. The yaml comment always said the human owns this call.

Also tried and rejected: `gpt-5-mini` on the same prompt and dataset scored **0.553 vs 0.656** and ran 4.5x slower (p50 3.9s -> 17.5s). It fixed `remote_ok` (0.40 -> 0.80) but collapsed `primary_roles` (0.62 -> 0.13) by emitting unsearchable variants like `data analyst (mid)` and `analytics engineer / dbt developer` — and those strings go straight into the job-search query. Its `skills` drop is partly the metric's fault, not the model's: it correctly added `flask` and `streamlit`, which are in the CV but missing from the label, and set-F1 punishes extra items.

## 2026-10-02 · locations and remote_ok were being guessed from CVs that cannot answer them

**Symptom.** `remote_ok` never scored above 0.600 and `locations` never above 0.800 in any extraction run. The failures made no sense as extraction errors: `junior_ds_in` says "Open to hybrid" (is that remote or not?), `senior_mle_in` says nothing at all about remote, and `lead_in_remote` lists four cities that are past offices, not places the candidate wants to work.

**Root cause.** These two fields are **preferences, not facts**. A CV records where someone has worked and sometimes where they live; it cannot say where they are willing to work or whether they want remote. The model was being graded on a question the document does not contain, so there was no right answer to converge on.

**Fix.** Stopped extracting both. The extraction prompt now says so explicitly. The Streamlit app asks the user instead ("Where do you want to work?" plus an "Open to remote roles" checkbox) and overrides the profile with `model_copy` before calling `run_search` — so `fetch_jobs` and `rank_jobs` keep reading `profile.locations` / `profile.remote_ok` with no signature changes anywhere in the graph. `run_batch.py`'s 7 cases now state both values explicitly, standing in for the user that a synthetic persona does not have. Both fields came out of `SCORED_FIELDS` and out of all 5 labels. `target_role` was the existing precedent for a user-supplied value overriding what the CV implies.

**Result.** Overall 0.656 -> 0.738, but **most of that is arithmetic**: dropping the two worst-scoring fields raises the mean on its own, the same way removing `languages` did. The scored set is now the four fields a CV can actually answer: seniority, years_experience, primary_roles, skills.

The real gain was accidental and elsewhere. `primary_roles` went **0.620 -> 0.770** because invented roles stopped appearing: `data architect`, `ml platform lead` and `ml ops engineer` all vanished, replaced by roles the candidate actually held. The cause is almost certainly a sentence added while scoping the two fields — "Extract only what the CV states ... do not infer" — which is unqualified and which the model generalised to every field.

That leaves a contradiction introduced by accident: the header now says "extract only what the CV states" while the `primary_roles` bullet still says "include the natural next step when their years justify it". The model is siding with the header, which improves precision but caps recall — the labels for `lead_in_remote` and `mid_analyst` deliberately include next-step roles (`principal data engineer`, `senior analyst`) that appear nowhere in those CVs, so full marks are now unreachable. Needs resolving on purpose, in one direction or the other.

## 2026-10-02 · The model's clock is frozen at its training cutoff, so "2022 - Present" was 3 years short

**Symptom.** `mid_analyst_in.pdf` scored 0.00 on `years_experience` in every single run: expected `4.0`, got `2.0`. Nothing moved it — not the field rewrite, not the worked examples, not switching to gpt-5-mini.

**Root cause.** Asked directly, gpt-4o-mini answers "Today's date is October 4, 2023" — its training cutoff. The extraction prompt never told it otherwise, so every date range ending in "Present" was computed against **2023**. "Data Analyst (2022 - Present)" came out as ~1-2 years instead of 4.

Four of the five fixture CVs hid this, because they state their experience in prose ("Data scientist with 2 years of experience...", "...with 8 years...", "...with 11 years..."), so the model just copied the number. `mid_analyst` is the only fixture with no such line, which is why it was the only one failing — and why a bug affecting **every production CV with a current job** showed up as a single stubborn fixture.

**Fix.** `extract_profile` now passes `datetime.now(UTC).date().isoformat()` into the prompt, which states that ranges ending in "Present", "Current" or "Now" run to that date. Reading from the system clock means it cannot go stale — the same failure mode that had made my own worked examples wrong (a hardcoded "2019 to present -> 6 years" that was 7 by the time I wrote it).

**Result.** `2.0` -> `4.0`. The date bug is fixed and verified.

**What it uncovered, still open.** 4.0 is the *current role only*. The honest total is 5 — Business Analyst (2021-2022) plus Data Analyst (2022-present), with the Analytics Intern year excluded for consistency with how `primary_roles` treats internships — so the label was corrected from 4.0 to 5.0. The model will not sum the roles. Three attempts failed: an explicit "add up EVERY relevant role, not just the current one" instruction, a worked example almost identical to the case itself, and a scratchpad reasoning field in the schema (which made it *worse*, 3.5, and listed the roles without adding them).

The diagnosis is that the arithmetic is the problem, not the reading. Asked the same question free-form with "show each role, its duration, whether you counted it and why", the model answers **5 years** correctly and shows the working. Through `with_structured_output` it will not. It reads date ranges reliably and adds them unreliably.

The principled fix is therefore to move the arithmetic out of the model: have it extract structured role periods (title, start year, end year or null for Present, whether the role is relevant) and compute `years_experience` in Python. Exact, reproducible, unit-testable without an API call, and it makes the "does the internship count" decision explicit instead of hidden inside a number. Deferred — it is a schema change plus every consumer, not a prompt tweak. The general lesson from both bugs in this entry: arithmetic does not belong in the model.

## 2026-10-02 · One LLM call fired 16 job searches, because the reformulated query was a list

**Symptom.** The tailoring batch report showed `"fetch_jobs: LLM issued 10 tool calls (expected 1); running all of them"` — and worse on inspection: `mid_analyst_in` issued **16** tool calls, twice in the same run (once per reformulation round), so roughly 32 searches for one case. It also returned the **fewest** jobs of any case, 10 against 25 for cases that issued 2 calls. More searching, less found.

**Root cause.** `reformulate_query`'s prompt said only "Try synonyms, adjacent job titles, or a less specific query so more jobs come back" — no constraint on shape or length, unlike the fetch prompt which demands one title of two to four words. So it generated this:

    'Data Analyst OR Business Analyst OR Analytics OR Data Scientist OR Data
     Specialist OR Reporting Analyst OR SQL OR Excel OR Looker OR Python OR DBT
     OR Snowflake OR Tableau OR Google Analytics OR Data Modeling OR Stakeholder
     Reporting'

16 OR-separated terms. That string lands in `state["search_query"]`, `fetch_jobs` puts it into its prompt verbatim as "Use this broader query and search again: ...", and the fetch model obediently issues **one tool call per term** — including for `SQL`, `Excel`, `Python` and `Snowflake`, which are skills, not job titles, and which boards match against titles and so return nothing.

Two things made it invisible. First, it only happens on a reformulation, so the first pass looks fine (verified: 1 tool call on the first pass, 16 on the reformulated one with the same profile). Second, the `_trim_query` guard added earlier the same day only cleans the query the *fetch* model returns per tool call — the reformulated query reaches the prompt as guidance **untrimmed**, bypassing it entirely. The same path is where the earlier `'Data Analyst OR Business Analyst OR'` search query came from.

And it is self-defeating: "broader" was implemented as *more terms*, but a list matches no posting at all, so the broadened query is strictly narrower than the single title it replaced. That is why the case with the most searches found the fewest jobs.

**Fix.** Two layers, matching the fetch path.
1. `REFORMULATE_PROMPT` now states the same contract: one job title someone would actually post, two to four words, reach for an adjacent or more general TITLE rather than more terms (`'senior data analyst' -> 'data analyst' -> 'business intelligence analyst'`), with worked bad examples. It says explicitly that a list is narrower than a single title, not broader.
2. `reformulate_query` runs its output through `_trim_query` before storing it, and records what was dropped in `errors`. A prompt is a request; this makes it a guarantee.

**Result.** Measured directly against the fetch model with the same profile:

| guidance query | tool calls |
|---|---|
| the 16-term OR list (before) | **16** |
| `'Business Intelligence Analyst'` (after) | **2** |

And the reformulation output itself is now a single searchable title every time: `mid_analyst` `'Data Analyst'` -> `'Business Intelligence Analyst'`, `junior_ds` `'data scientist'` -> `'data analyst'`, `career_changer` `'data analyst'` -> `'business intelligence analyst'`. The prompt change alone was enough — `_trim_query` did not have to intervene on any of the three, so it is now a backstop rather than the mechanism. Pinned by two tests in `tests/test_fetch_query.py`.

Still open, deliberately: the remaining 2 calls are the **same query twice**, which is pure waste. Deduping identical `(query, country, remote)` tuples before searching would fix it, and `ensure_budget` still counts only the 1 LLM call rather than the N search requests it authorises — which matters because Jooble's quota is 500 requests for the lifetime of the key.

## 2026-10-02 · The fabrication validator reported 39%; about 2% was real

**Symptom.** The first tailoring batch (14 cases, 371 claims) reported `fabrication_rate: 0.388`, with every one of 13 tailored runs flagged. A model that invents 4 lines in 10 would be unusable — but reading the flags, almost none were inventions.

**Root cause.** Three separate faults, all producing false alarms.

1. *Stage 1 cannot tell direction.* The deterministic gate scores `difflib` similarity against the source and flags anything under 0.65. Honest summarisation scores low — "Migrated a critical Airflow DAG delivering company/account data to Salesforce CRM into a Databricks workflow, reducing latency by 40%" became "Migrated critical workflows from Airflow to Databricks, reducing data processing latency by 40%", nothing invented, ratio 0.55, flagged. All 99 deterministic flags were on prose, and every one inspected was a summary, not an invention.
2. *The LLM judge flagged omission, which its own prompt forbids.* At least 23 of its 45 flags said "the rewrite omits...", against three explicit sentences in the prompt ("omission is never a problem", "Never flag a rewrite for what it does not say"). Some were worse than omission: "rewriting correlated subqueries" against a source saying "rewriting three correlated subqueries" was flagged as having *added* a detail — the direction of the comparison reversed. An earlier entry in this log records this omission problem as fixed by prompt wording. It was not; nothing had re-measured it, because this batch did not exist yet.
3. *The corpus split a sentence mid-number.* "...at a p99 latency of" / "45ms." became two corpus items, because the line-join rule only treated a lowercase first letter as a continuation, and a digit is not lowercase. No single source contained the full fact, so the judge was correctly told "45ms" was absent from the source it was shown — four times.

The judge was also the same model as the writer it grades (`gpt-4o-mini` for both).

**Fix.**
- `corpus.py`: a line starting with a digit now continues the previous line, like a lowercase one does. `45ms` rejoins its sentence.
- `drift_check.py`: one stated rule — flag only for something the rewrite *states* that the source does not support; leaving things out is always fine — plus eight worked examples, four grounded (number dropped, `40M -> millions`, count dropped, synonym) and four not (added tool, changed number, invented outcome, inflated role). The examples are synthetic and from other domains, so a re-run cannot pass by memorising the claims it is measured on. The reason must now quote the exact unsupported phrase from the rewrite.
- The judge model is a setting, `JOBLYST_JUDGE_MODEL`, defaulting to `gpt-4.1` — deliberately stronger than the tailoring model.
- Judge calls now run at most 3 at a time with retry and backoff. Each few-shot call is ~640 tokens and this account allows gpt-4.1 30,000 tokens per minute. (Corrected later: I first wrote that one CV's claims fired at once caused HTTP 429. It did not — the 429 came from a test script judging 45 claims from several CVs at once, ~29k tokens. Measured, one CV needs ~16 judge calls, ~10k tokens.)

**Result.** Re-judged the same 45 claims the old judge had flagged, only the judge changing, with prompt and model separated:

| judge | still flagged |
|---|---|
| old prompt + gpt-4o-mini | 40 / 45 |
| new prompt + gpt-4o-mini | 32 / 45 |
| **new prompt + gpt-4.1** | **7 / 45** |

All 7 survivors are genuine, each quoting an invented phrase: "fostering a strong understanding of data analysis concepts", "improving educational outcomes and student performance", "through innovative teaching methods and data analysis", "Managed and optimized ... enhancing data accessibility". No omission flags remain. The worked examples alone barely moved the small model; the model change did most of the work.

Pattern worth noting: every real fabrication is unsupported *qualitative* padding — invented outcomes and causes on the career-changer's teaching bullets, inflated verbs on the analyst's. None invented a tool or changed a number. That is where this tailoring prompt is weak.

**Trade-off, accepted deliberately.** Fabrication checking went from ~1.6s (gpt-4o-mini, unlimited parallelism, measured over 16 runs) to slower — a bigger model per call, and capped parallelism. Judged acceptable: tailoring is a one-off action the user already waits ~14s for, and a check that flags 39% of lines trains users to ignore it, which hides the 2% that matter.

**Full batch re-run (14 cases, 383 claims), new judge.** It only half-worked:

| | before | after |
|---|---|---|
| LLM-judge flags | 45 | **16** |
| deterministic flags | 99 | 74 |
| fabrication rate | 0.388 | **0.235** |

The judge is fixed: of its 16 flags, 14 are genuine qualitative padding and 2 come from the one corpus split still left (a wrapped line starting with a capital — `...conversation threads with` / `PostgreSQL checkpointing...`). But the 45-claim re-judge only ever measured stage 2. The deterministic stage was never changed and now produces 74 of the 90 flags, still on honest summaries (e.g. a churn-model bullet reworded at similarity 0.645). Real rate by reading every LLM flag: about 14 / 383 = **3.7%**. Next step: stop the deterministic stage judging prose and keep it for skills only.

A counting mistake of my own, recorded so it is not repeated: a keyword search for omission language reported 9 of the 16 as omission flags. It was matching "the source does not mention", which the judge uses to explain an *added* phrase. Reading them, none were omissions.

**Latency and cost, measured.** Median fabrication-check time per CV went from **1.7s to 4.1s** (max 5.4s, 14 runs) — far less than the 10-20s estimated beforehand. The whole 14-case batch went from **$0.065 to $0.29**, and almost all of the rise is the judge: gpt-4.1 $0.245 (85%), the tailoring writer gpt-4o-mini $0.012 (4%), search and ranking $0.033 (11%). Checking a CV now costs about 21x what writing it does, though still under 2 cents. No rate-limit failures; no crashes.

A measurement error corrected here: costs reported earlier for these batches ($0.11 old, $0.32 new) were wrong. Opik's `tags contains "tailor-batch"` filter matches substrings, so it also picked up every `tailor-batch-search` trace and counted the search cost twice. The same thing explained the "twice as many traces as runs" oddity, which I had wrongly guessed was the judge opening its own traces. Grouping by the exact tag set gives the figures above.


## 2026-10-03 · The similarity gate now checks skills only; all prose goes to the judge

**Symptom.** After the judge fix the rate was 0.235, but 74 of the 90 flags came from the deterministic similarity gate, which still ran first on every prose claim and still flagged honest summaries (a churn-model bullet shortened at similarity 0.645).

**Root cause.** The gate measures string similarity, not direction, so shortening looks the same as inventing. It could not be tuned out of this: lowering the threshold would also let through the one-character number changes the judge exists to catch.

**Fix.** `validate_pack_hybrid` no longer applies any similarity threshold to prose. Skills keep the deterministic exact-match check — a vocabulary lookup has no judgment in it. Every bullet, summary sentence, cover-letter sentence and the headline goes to the gpt-4.1 judge. Similarity is still *used*, but only to choose which CV lines to show the judge for prose with no citation. One deterministic check is kept deliberately: a bullet citing a corpus id that does not exist is flagged without an LLM call, because that is a fact, not a judgment.

Considered first and rejected: `gpt-4.1-mini` as a cheaper judge. On the same 45 claims it left 17 flagged against gpt-4.1's 7, and the extra ten were mostly the kinds of change the worked examples call fine ("drastically reducing build time" for "7 hours to 95 minutes", and one near-verbatim copy of its source). It has 6.7x the rate-limit headroom (200k tokens per minute vs 30k), but re-creating the false alarms defeats the point.

**Result.** Full 14-case batch:

| batch | flags | rate | median check time | judge cost |
|---|---|---|---|---|
| similarity gate on all prose | 90 / 383 | 0.235 | 4.1s | $0.245 |
| **similarity gate on skills only** | **38 / 364** | **0.104** | **5.8s** | **$0.413** |

Read by hand, about **21 of the 38 are real** (5.8%): the same qualitative padding, two invented facts about the hiring company in cover letters, and one genuine number distortion — a cover letter saying a model was "successfully flagging 23 students" where the CV says it identified 23 and 19 were correct.

**New weakness surfaced, not fixed.** About 17 of the 38 are false, and most share one cause: for prose with no citation, the judge is shown only the 3 CV lines with the highest `difflib` similarity, and that pick is often wrong. "With over 11 years of experience in data engineering" was flagged as "none of the sources mention the number of years", while the CV opens "Lead data engineer with 11 years of experience" — that line simply was not among the 3 shown. Similarly a headline "specializing in GenAI and Agentic AI" was flagged although "agentic ai" is in the CV's skills. The gate used to hide this by flagging these sentences on similarity before the judge saw them.

Tested a fix, not yet wired in: choose the source lines with embeddings (`text-embedding-3-small`, cosine similarity) instead of `difflib`. For the three wrongly flagged sentences, the CV line that proves each one ranked #20, #16 and #24 by `difflib` and **#1** by embeddings in all three. `difflib`'s score divides by total length, so a long line that says almost the same thing loses to short, loosely related lines — the headline "Junior Data Engineer specializing in GenAI and Agentic AI" is nearly a copy of a CV line that `difflib` ranked 16th of 50.

**Rate limits, measured.** 218 judge calls across the batch, **0 failed** — no 429 at all, so the backoff never fired. One CV averaged 16 judge calls (max 21), ~10k tokens, judged in ~6s; the rest of each case is searching and writing, so any 60-second window holds about one CV's judging, well under the 30k-per-minute limit. The retry is insurance for concurrent users, who share the account-wide budget.

Also noticed while explaining the code, not yet fixed: LangChain's `with_retry` defaults to `retry_if_exception_type=(Exception,)`, so permanent errors such as a malformed request or a bad API key are retried eight times with growing waits before failing. It should retry only on rate-limit, timeout and connection errors.

## Known limitations (not yet fixed)

- **Non-standard Title Case headings.** `Certifications` written in Title Case
  is not recognised as a heading, so its contents merge into the section above.
  All-caps `CERTIFICATIONS` works. Visible in `senior_mle_in`, where education
  ends up with 5 items instead of 2.
- **Unrecognised skills headings.** `TECHNICAL PROFICIENCIES` is not matched as
  a skills heading, so that CV parses 0 skills. The fallback added above keeps
  validation correct, but the skills are categorised as experience.
- **Profile extraction ignores its own "leave empty" instruction.** The prompt
  for `Profile.projects` says to leave it empty when the CV has no Projects
  section, but on 3 of 5 fixture CVs (`lead_in_remote`, `mid_analyst_in`,
  `senior_mle_in` — none of which have a Projects section) the model filled it
  anyway, lifting achievement bullets straight out of Experience. Negative
  instructions ("leave empty if...") are weaker than positive ones for an LLM to
  follow reliably. Low real-world impact today since `profile.projects` is only
  read by the `target_role` domain-pivot branch in `fetch_jobs.py`, which none
  of these three candidates use — but worth fixing with a positive, concrete
  rule ("only pull from a section headed Projects/Personal Projects; never from
  Experience") before trusting the field for its intended purpose. Needs a
  before/after regression check across all 5 fixture CVs when it's fixed, not
  a spot check on one — this is exactly what `ProfileFieldAccuracy` /
  `expected_profiles.yaml` is for, once that eval exists.
- **Adzuna job descriptions are cut to 500 characters, so the ranker scores
  partial postings without knowing it.** Adzuna's API returns only a
  500-character snippet, ending mid-sentence with "…". A live call returned
  10 of 10 results at exactly 500 characters, and all 50 Adzuna postings in
  `data/cached_jobs.json` are exactly 500 (Himalayas and Remotive run up to
  4000). Our own limit is 4000 (`DESCRIPTION_LIMIT` in `search_job.py`), and the
  ranker reads the first 1500 characters, so neither is the cause. Adzuna is
  most of the India data, so most ranked jobs are affected.
  What goes wrong: a requirement that appears after character 500 ("5+ years",
  "Databricks mandatory", "early-career not a fit") is invisible, and nothing in
  the prompt says the text is partial, so the model treats a missing
  requirement as no requirement. It falls back on title cues ("Senior", "L3",
  "Advanced") and sometimes invents gaps. The experience-gap rule cannot fire
  when the years figure is in the hidden part. Seen while labeling
  `joblyst-ranking-cases`: the Honeywell "Advanced Data Scientist" and
  Deutsche Bank "L3" roles were both scored 60 for junior candidates.
  Options, cheapest first: (1) tell the prompt the text may be cut off and not to
  assume a requirement is absent; (2) fetch the full page from Adzuna's
  `redirect_url` for ranked jobs (real text, but one extra request per job, and
  those pages may block scrapers, untested); (3) lean on sources that return
  full text (mostly remote jobs, not India). Measure any fix against the
  labeled ranking set before and after.
  Tried and not adopted (2026-09-21): a prompt rule marking cut-off descriptions
  and judging seniority from the job title, with the ranker told which postings
  are cut off. On the 46 labeled items it fixed 2 misses (Honeywell Advanced
  Data Scientist, Deutsche Bank L3 Data Engineer) and broke 2 (Capco Data
  Engineer, where the model treated the missing text itself as a reason to
  score lower, and Priya's Senior Data Analyst, where it used the profile's
  `mid` label and ignored her 11 years). Net change 0.891 to 0.891. The full
  posting cannot be fetched (Adzuna's redirect pages return 403), so this stays
  a data limit of the free API.
