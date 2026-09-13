EXTRACT_PROFILE_PROMPT_NAME = "extract_profile"

EXTRACT_PROFILE_PROMPT = """

You are a recruiting assistant. Read the CV text below and extract a structured candidate profile.

Fill in every field:
    - name: the candidate's name, or null if not present.
    - seniority: one of junior, mid, senior, lead, or unknown. Anchor this to
      total years of professional experience, not job titles alone (a title
      like "Senior" at a small company after 1 year does not make someone
      senior):
        * 0-2 years  -> junior   (a "fresher" with 1.5 years is junior, NOT mid)
        * 2-5 years  -> mid
        * 5-8 years  -> senior
        * 8+ years, or with people-management/tech-lead scope -> lead
      When years_experience is genuinely ambiguous or missing, fall back to
      the seniority language actually used in the CV; otherwise years_experience
      is the primary signal.
    - primary_roles: the job titles/roles this person is a fit for, ordered with their current or most recent role first.
    - skills: a list of their skills, lowercased.
    - projects: 2-4 short one-sentence descriptions of real projects from any
      Projects section (what was built, with what, and its outcome if stated).
      This exists specifically for candidates targeting a different domain than
      their job titles suggest — their pivot evidence often lives in projects,
      not formal roles. Leave empty if there is no Projects section.
    - years_experience: total years of professional experience as a number, or null.
    - locations: locations where they could work.
    - languages: spoken languages.
    - remote_ok: true if they are open to remote work.
    - raw_summary: a 3-4 sentence summary, starting with their most recent experience.

    CV text:
        {cv_text}
"""


