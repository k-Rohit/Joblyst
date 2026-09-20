DRIFT_CHECK_PROMPT_NAME = "drift_check"

DRIFT_CHECK_PROMPT = """

A rewritten claim and its real source(s) are given below. The rewrite already \
scored as similar overall — your only job is to check for one specific kind of problem a \
similarity score can miss: a number, tool, or detail that was changed or added, hidden inside \
otherwise-faithful wording.

Rewrite:
{rewrite}

Real source(s):
{sources}

If every number, tool, and detail in the rewrite is actually present in the source(s), it's grounded. \
If anything was changed (e.g. a bigger number) or added (e.g. a tool never mentioned), it's not.

Judge ONLY in that direction. A rewrite is free to leave things out, shorten, generalize, or \
mention only part of the source — omission is never a problem. Never flag a rewrite for what it \
does not say, only for a detail it states that the source does not support.
"""
