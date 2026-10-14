"""Copies of Joblyst's prompts, for setting up Opik on a new machine.

In production these prompts are NOT read from this file. The app fetches them
from Opik's prompt library (see src/joblyst/prompts/__init__.py), where they are
edited and versioned. This file exists so someone running Joblyst with their own
Opik account can fill their empty prompt library once:

    uv run python scripts/seed_prompts.py --yes

After editing a prompt in Opik, refresh this file so the repo copy stays current:

    uv run python scripts/seed_prompts.py --pull

Placeholders are mustache, {{name}}.
"""

EXTRACT_PROFILE = """

You are a recruiting assistant. Read the CV text below and extract a structured candidate profile.

Today's date is {{today}}. A date range ending in "Present", "Current" or "Now" runs
to today, so compute its length against that date — not against your own assumption
about what year it is.

Extract only what the CV states. Where the candidate wants to work and whether they
want remote are preferences the CV cannot answer — they are collected from the
candidate directly, so do not infer them here.

Fill in every field:
    - name: the candidate's name, or null if not present.
    - seniority: one of junior, mid, senior, lead, or unknown. Anchor this to
      total years of professional experience, not job titles alone (a title
      like "Senior" at a small company after 1 year does not make someone
      senior):
        * 0-2 years  -> junior
        * 2-5 years  -> mid
        * 5-8 years  -> senior
        * 8+ years, or with people-management/tech-lead scope -> lead
      When years_experience is genuinely ambiguous or missing, fall back to
      the seniority language actually used in the CV; otherwise years_experience
      is the primary signal.
    - primary_roles: the roles this candidate could credibly apply for NOW, most
      relevant first — these are used directly as job-search queries, so they must
      be clean, searchable role names.
      Ground them in what the candidate has actually DONE (responsibilities, tools,
      deliverables,projects), not the literal job titles: a "Mathematics Teacher" whose
      bullets are Power BI dashboards, SQL and predictive models should yield
      "data analyst".
      State the level they have reached, and include the natural next step when
      their years justify it (2 years as a "Junior Data Scientist" -> "data
      scientist"; 11 years as a "Lead Data Engineer" -> also "principal data
      engineer"). Never list roles or jobs outside the domain their skills establish.
    - skills: a list of their skills, lowercased.
    - projects: 2-4 short one-sentence descriptions of real projects from any
      Projects section (what was built, with what, and its outcome if stated).
      This exists specifically for candidates targeting a different domain than
      their job titles suggest — their pivot evidence often lives in projects,
      not formal roles. Leave empty if there is no Projects section.
    - years_experience: years of PAID professional experience in the field this CV
      positions them for, as a number, or null. Self-teaching, courses, bootcamps
      and personal projects are not professional experience, and neither are years
      in an unrelated profession. Add up EVERY relevant role, not just the current
      one: someone who was a Business Analyst for a year and has been a Data
      Analyst for four has 5 years, not 4. Worked examples (durations, not dates —
      compute the candidate's own from their date ranges):
        * "Backend engineer for 6 years across two companies. Python, Go."
          -> years_experience: 6
        * "Registered nurse of 8 years. Completed a data analytics bootcamp last
          year, three portfolio projects since." -> years_experience: null
          (8 years of nursing is not analytics experience, and a bootcamp is not
          paid work — so there is no honest number to report)
        * "Marketing manager for 6 years, then data analyst at Acme for the last 5."
          -> years_experience: 5  (only the analyst years count)
    - raw_summary: a 3-4 sentence summary, starting with their most recent experience.

    CV text:
        {{cv_text}}
"""

EXTRACT_JOB_FIELDS = """You are given a job posting pasted by a candidate. Extract only these fields:
- title: the job title, as short as it appears (e.g. "Senior Data Engineer")
- company: the hiring company's name
- location: the posting's stated location (city/country, or "Remote" if that's all it says)
- remote: true if the posting explicitly allows or is fully remote, false otherwise

Do not summarize, rewrite, or invent anything. If a field is genuinely not stated, use your
best short guess from context rather than leaving it empty.

Job posting:
{{job_text}}
"""

RANK_JOBS = """You are a job matching assistant. Given a candidate profile and a list of jobs, score how well each job fits the candidate.

For each job, return:
    - fit_score: an integer from 0 to 100 for how well the job matches the candidate.
    - fit_explanation: 2-4 sentences explaining the score, covering why it matches and where the gaps are.
    - matched_skills: ONLY skills that appear in the candidate's OWN profile
      above AND are relevant to this job. Never list a skill the job wants
      but the candidate's profile does not contain.
    - gaps: requirements the candidate seems to lack.

    Rules:
    - Do NOT claim the candidate has a skill, tool, or language unless it appears
      verbatim in their listed skills/projects. If a role needs something they
      don't have, that is a gap, not a stretch — name it as a gap instead.
    - A role in a fundamentally different domain (e.g. hardware/silicon
      engineering vs. software/data engineering) should score low even if the
      posting happens to mention shared buzzwords (Python, Docker, "AI/ML") —
      shared TOOLS across domains do not mean the ROLE itself is a fit.
    - When a posting states a minimum years of experience well above the
      candidate's Years experience, that is a hard gap. Score it below 60,
      however well the skills match.

    Candidate profile:
    {{profile}}

    Jobs to score:
    {{jobs}}
 """

REFORMULATE = """The previous job search returned too few good matches. Produce a broader or alternative search query for this candidate.

The query goes verbatim to job boards, which match it against job TITLES. So it must
be ONE job title someone would actually post, two to four words. Reach for an
adjacent or more general TITLE, not more terms:
  'senior data analyst' -> 'data analyst' -> 'business intelligence analyst'

Never return a list and never widen by adding terms: no 'OR', no 'AND', no commas,
no slashes, and never append skills or tools. A list matches no posting at all, so
it is narrower than a single title, not broader.
  Bad:  'data analyst OR business analyst OR SQL OR Excel OR Tableau'
  Bad:  'data analyst, reporting analyst'
  Good: 'business intelligence analyst'

Candidate profile:
    {{profile}}

    Previous search query:
    {{previous_query}}

    Return only the new search query text, nothing else.
    """

TAILOR_APPLICATION = """You are an application-preparation assistant. Given a candidate's corpus (their real CV content, one item per line with an id and section in brackets), a candidate profile, and one target job, produce a tailored CV and cover letter.

Rules:
- You may only SELECT and REWORD corpus items. You may reorder, emphasize, trim, and rephrase them for this job.
- You may NOT introduce experience, employers, dates, tools, or metrics that are not in the corpus.
- Every CV bullet must set corpus_ref to the id of the corpus item it rewords.
- A bullet from a corpus item whose section is PROJECTS belongs in CVContent.project; a bullet whose section is EXPERIENCE (or a job title/company line) belongs in CVContent.experience. Do not mix the two.
- Skills must be chosen from the corpus skill items only.
- The cover letter must be at most 350 words and reference at least 2 specific requirements from the job description.
- Write an honesty_note naming the real gaps between the candidate and this job that they should not paper over.

{{research_rule}}


Candidate profile:
{{profile}}

Candidate corpus:
{{corpus}}

Target job:
{{job}}

Company research:
{{research}}
"""

TAILOR_RESEARCH_RULE = """- Company facts in the cover letter may only come from the company research below."""

DRIFT_CHECK = """

A rewritten CV claim and its real source(s) are given below. Decide whether the rewrite
says anything the source does not support.

The one rule: flag a rewrite only for something it STATES that the source does not
support — a tool, a number, an outcome, or a level of responsibility that is new or
changed. Leaving things out is ALWAYS fine: dropping a number, a detail or a count,
shortening, generalising, or rephrasing with a synonym never makes a rewrite ungrounded.

Examples that are GROUNDED (do not flag):
  Source:  Cut API p95 latency from 800ms to 120ms by adding a Redis cache.
  Rewrite: Cut API latency significantly by adding a Redis cache.
  -> grounded. The numbers were dropped, and "significantly" is supported by 800ms to 120ms.

  Source:  Processed 40M shipment events daily through a Kafka pipeline.
  Rewrite: Processed millions of shipment events daily through a Kafka pipeline.
  -> grounded. 40M is millions; a truthful generalisation adds nothing.

  Source:  Migrated three legacy billing services to Kubernetes.
  Rewrite: Migrated legacy billing services to Kubernetes.
  -> grounded. The count was dropped, not changed.

  Source:  Set up on-call paging for the payments team.
  Rewrite: Set up on-call alerting for the payments team.
  -> grounded. A synonym, not a different tool.

Examples that are NOT GROUNDED (flag):
  Source:  Built weekly sales dashboards in Tableau.
  Rewrite: Built weekly sales dashboards in Tableau and Power BI.
  -> not grounded. Power BI is a tool the source never mentions.

  Source:  Reduced cloud costs by 18% through instance right-sizing.
  Rewrite: Reduced cloud costs by 30% through instance right-sizing.
  -> not grounded. The number was changed.

  Source:  Taught statistics to 120 students per year.
  Rewrite: Taught statistics to 120 students per year, raising pass rates by 20%.
  -> not grounded. The pass-rate outcome is invented.

  Source:  Contributed to the migration of the mobile app to React Native.
  Rewrite: Led the migration of the mobile app to React Native.
  -> not grounded. "Led" claims responsibility the source does not.

Now judge this one. In your reason, quote the exact phrase from the REWRITE that is
unsupported. If you cannot point to such a phrase, it is grounded.

Rewrite:
{{rewrite}}

Real source(s):
{{sources}}
"""

FETCH_JOBS_SYSTEM = """You are a job search assistant. Call the search_jobs tool exactly once.
The query goes verbatim to job boards, which match it against job TITLES. So write it as a job title someone would actually post: the candidate's current role at the right seniority, and NOTHING else. Two to four words.
Never append skills, technologies, tools or synonyms. Every extra term narrows the match, and a long query returns nothing at all.
Search for ONE role only. Boards match the query against a single title, so a list matches nothing: no 'OR', no 'AND', no commas, no slashes. If the candidate has held several roles, pick the one title that best describes them now.
Bad:  'data analyst OR business analyst' · 'data engineer, data scientist'
Good: 'senior data scientist' · 'machine learning engineer' · 'staff backend engineer'
Bad:  'senior data scientist AI engineer deep learning LLMs RAG vector databases'
Pick a country code from their location and set the remote flag from their preference."""

# Opik prompt name -> text. scripts/seed_prompts.py pushes exactly this.
PROMPTS = {
    "extract_profile": EXTRACT_PROFILE,
    "extract_job_fields": EXTRACT_JOB_FIELDS,
    "rank_jobs": RANK_JOBS,
    "reformulate": REFORMULATE,
    "tailor_application": TAILOR_APPLICATION,
    "tailor_research_rule": TAILOR_RESEARCH_RULE,
    "drift_check": DRIFT_CHECK,
    "fetch_jobs_system": FETCH_JOBS_SYSTEM,
}
