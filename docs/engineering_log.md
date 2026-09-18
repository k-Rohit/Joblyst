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

## Known limitations (not yet fixed)

- **Non-standard Title Case headings.** `Certifications` written in Title Case
  is not recognised as a heading, so its contents merge into the section above.
  All-caps `CERTIFICATIONS` works. Visible in `senior_mle_uk`, where education
  ends up with 5 items instead of 2.
- **Unrecognised skills headings.** `TECHNICAL PROFICIENCIES` is not matched as
  a skills heading, so that CV parses 0 skills. The fallback added above keeps
  validation correct, but the skills are categorised as experience.
