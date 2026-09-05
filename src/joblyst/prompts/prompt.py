EXTRACT_PROFILE_PROMPT_NAME = "extract_profile"

EXTRACT_PROFILE_PROMPT = """

You are a recruiting assistant. Read the CV text below and extract a structured candidate profile.

Fill in every field:
    - name: the candidate's name, or null if not present.
    - seniority: one of junior, mid, senior, lead, or unknown.
    - primary_roles: the job titles/roles this person is a fit for, ordered with their current or most recent role first.
    - skills: a list of their skills, lowercased.
    - years_experience: total years of professional experience as a number, or null.
    - locations: locations where they could work.
    - languages: spoken languages.
    - remote_ok: true if they are open to remote work.
    - raw_summary: a 3-4 sentence summary, starting with their most recent experience.

    CV text:
        {cv_text}
"""

