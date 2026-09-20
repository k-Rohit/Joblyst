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
