"""Prompt for the query-reformulation node (see prompts/__init__.py)."""

REFORMULATE_PROMPT_NAME = "reformulate"

REFORMULATE_PROMPT = """The previous job search returned too few good matches. Produce a broader or alternative search query for this candidate.

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
    {profile}

    Previous search query:
    {previous_query}

    Return only the new search query text, nothing else.
    """