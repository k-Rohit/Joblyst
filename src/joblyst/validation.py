""" 
Deterministic fabrication validator.

``validate_pack`` checks every claim in a ``TailoringPack`` against the
candidate corpus with plain string similarity — no LLM, no cost, same result
every run. It flags what it cannot ground; it never retries or repairs. Flags
flow to state, trace metadata, and a visible UI warning.

"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from joblyst.config import get_settings
from joblyst.corpus import CandidateCorpus
from joblyst.schemas.schemas import FabricationReport, FlaggedClaim, TailoringPack

_MIN_FACTUAL_SENTENCE_WORDS = 6  # shorter sentences are treated as unverifiable fluff, not claims
_MIN_SKILL_TOKEN_CHARS = 4  # ignore tiny words (e.g. "a", "of") when checking skill-word containment

_PUNCT = re.compile(r"[^\w\s]")  # matches any punctuation character, for stripping it out
_WS = re.compile(r"\s+")  # matches runs of whitespace, for collapsing them to one space

_NUM_SUFFIXES = {"k": "thousand", "m": "million", "bn": "billion", "b": "billion"}  # numeric shorthand -> spelled-out word
_NUM_SUFFIX_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(bn|k|m|b)\b")  # matches "10m", "2.5bn", etc.
_PER_RE = re.compile(r"\bper\s+(\w+)\b")  # matches "per day" so it can collapse to just "day"
_FREQ_WORDS = {"daily": "day", "weekly": "week", "monthly": "month", "yearly": "year", "annually": "year", "hourly": "hour"}  # frequency adverb -> matching noun

def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, canonicalize units.

    Canonicalization: numeric suffixes expand (10m -> 10 million), "per X"
    collapses to "X" (punctuation already turned "/day" into "day"), and
    frequency adverbs map to their nouns (daily -> day).
    """
    text = _WS.sub(" ", _PUNCT.sub(" ", text.lower()))
    text = _NUM_SUFFIX_RE.sub(lambda m: f"{m.group(1)} {_NUM_SUFFIXES[m.group(2)]}", text)
    text = _PER_RE.sub(r"\1", text)
    return " ".join(_FREQ_WORDS.get(word, word) for word in text.split()).strip()

def _ratio(a: str, b: str) -> float:
    """ Similarity of two strings after normalization (0..1) """
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()

def _best_ratio(text: str, references: list[str]) -> float:
    """Compare ``text`` against every reference and return the single best match.

    We only need ONE reference to ground a claim, not all of them — a bullet
    is honest if it matches even one real corpus item well, regardless of how
    poorly it matches everything else. So the question is always "what's the
    best match found so far," not an average across all references.
    """
    return max((_ratio(text, ref) for ref in references), default=0.0)


def _best_pair_ratio(text: str, references: list[str]) -> float:
    """Check whether ``text`` is honest even when no SINGLE reference covers it alone.

    Example: a cover-letter sentence might say "built a RAG system processing
    2M+ records" by combining one corpus bullet about the RAG system with a
    different bullet mentioning the record count. Neither bullet alone would
    score well against that sentence in ``_best_ratio``, even though the claim
    is entirely real — it's just assembled from two places.

    To catch this cheaply (without comparing every possible pair of the
    corpus, which could be huge), we first narrow to the 3 references that
    already scored best individually, then try concatenating pairs of those
    three together — in both orders, since "A then B" and "B then A" can read
    very differently — and take whichever combination matches best.
    """
    top = sorted(references, key=lambda ref: _ratio(text, ref), reverse=True)[:3]
    return max((_ratio(text, f"{a} {b}") for a in top for b in top if a is not b), default=0.0,)



