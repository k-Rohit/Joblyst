"""Prompt for pulling structured metadata out of a pasted job posting.

Only short, checkable facts are extracted (title, company, location, remote).
The description itself is never generated or reproduced by the model — it is
assigned directly from the pasted text in code, so it can never drift from
what the poster actually wrote (see corpus.py for the same principle applied
to CV text).
"""

EXTRACT_JOB_PROMPT_NAME = "extract_job_fields"

EXTRACT_JOB_PROMPT = """You are given a job posting pasted by a candidate. Extract only these fields:
- title: the job title, as short as it appears (e.g. "Senior Data Engineer")
- company: the hiring company's name
- location: the posting's stated location (city/country, or "Remote" if that's all it says)
- remote: true if the posting explicitly allows or is fully remote, false otherwise

Do not summarize, rewrite, or invent anything. If a field is genuinely not stated, use your
best short guess from context rather than leaving it empty.

Job posting:
{job_text}
"""
