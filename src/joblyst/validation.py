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

def _looks_factual(sentence: str) -> bool:
    """Whether a cover-letter sentence makes a checkable claim.

    A digit (metrics, years) or a capitalized multi-word token mid-sentence
    (product/company/tool names) marks a sentence as factual. Everything else
    (motivation, enthusiasm) is unverifiable by design and skipped.
    """
    if len(sentence.split()) < _MIN_FACTUAL_SENTENCE_WORDS:
        return False
    if re.search(r"\d", sentence):
        return True
    return bool(re.search(r"\b[A-Z][a-z]+ [A-Z][a-z]+", sentence[1:]))


def _split_sentences(text: str) -> list[str]:
    """Naive sentence split on newlines and ., ! and ? boundaries.

    Newlines split too because greetings ("Dear team,") end without sentence
    punctuation and would otherwise swallow the following claim.
    """
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def check_skills(skills: list[str], corpus: CandidateCorpus, skill_ratio: float) -> list[FlaggedClaim]:
    """Ground each claimed skill against the corpus vocabulary. Never uses an LLM.

    A skill is a vocabulary lookup, not a judgment call, so a second opinion
    would add cost and drift for nothing. Shared by both validators so the
    deterministic answer can't differ between them.

    When segmentation parsed no skills section at all, fall back to grounding
    each skill's words in the full corpus text — otherwise an unrecognized
    heading ("TECHNICAL PROFICIENCIES") flags every genuinely-real skill at 0.00.
    """
    corpus_skills = corpus.skills()
    full_corpus_text = _normalize(" ".join(item.text for item in corpus.items))
    flagged: list[FlaggedClaim] = []

    for skill in skills:
        if corpus_skills:
            best = _best_ratio(skill, corpus_skills)
            # Containment: claiming LESS than the corpus states is honest —
            # "AWS" is grounded by "basic AWS". The reverse (adding qualifiers
            # the corpus never made) still has to pass the ratio.
            claimed = set(_normalize(skill).split())
            contained = bool(claimed) and any(claimed <= set(_normalize(cs).split()) for cs in corpus_skills)
            if best < skill_ratio and not contained:
                flagged.append(
                    FlaggedClaim(
                        where=f"skill:{skill}",
                        text=skill,
                        reason=f"skill is not in the candidate's corpus (best match {best:.2f})",
                        best_match_ratio=round(best, 3),
                    )
                )
        else:
            tokens = [t for t in _normalize(skill).split() if len(t) >= _MIN_SKILL_TOKEN_CHARS]
            missing = [t for t in tokens if t not in full_corpus_text]
            if missing:
                found = 1 - len(missing) / len(tokens) if tokens else 0.0
                flagged.append(
                    FlaggedClaim(
                        where=f"skill:{skill}",
                        text=skill,
                        reason=(
                            "no skills section was parsed from the CV, and these words appear "
                            f"nowhere in its text: {', '.join(missing)}"
                        ),
                        best_match_ratio=round(found, 3),
                    )
                )
    return flagged


def validate_pack(
    pack: TailoringPack,
    corpus: CandidateCorpus,
    research_notes: str | None = None,
    job_context: list[str] | None = None,
) -> FabricationReport:
    """Check every claim in the pack against the corpus. Deterministic, no LLM.

    ``job_context`` (e.g. job title and company) is added to the cover-letter
    reference texts so "I am applying for X at Y" is not flagged.
    """
    settings = get_settings()
    bullet_ratio = settings.fab_bullet_ratio
    skill_ratio = settings.fab_skill_ratio
    letter_ratio = settings.fab_letter_ratio
    flagged: list[FlaggedClaim] = []
    claims_checked = 0

    def check_bullet(bullet) -> None:
        nonlocal claims_checked
        claims_checked += 1
        item = corpus.get(bullet.corpus_ref)
        if item is None:
            flagged.append(
                FlaggedClaim(
                    where=f"cv_bullet:{bullet.corpus_ref}",
                    text=bullet.text,
                    reason="corpus_ref does not resolve to any corpus item",
                )
            )
            return
        ratio = _ratio(bullet.text, item.text)
        if ratio < bullet_ratio:
            flagged.append(
                FlaggedClaim(
                    where=f"cv_bullet:{bullet.corpus_ref}",
                    text=bullet.text,
                    reason=f"rewrite drifted too far from its corpus item (ratio {ratio:.2f} < {bullet_ratio})",
                    best_match_ratio=round(ratio, 3),
                )
            )

    # 1. CV bullets: the corpus_ref must resolve and the rewrite must stay close.
    #    Both experience and project bullets are checked the same way.
    for entry in pack.cv.experience:
        for bullet in entry.bullets:
            check_bullet(bullet)
    for entry in pack.cv.project:
        for bullet in entry.project_bullets:
            check_bullet(bullet)

    # 2. Skills: must come from the corpus skill vocabulary.
    claims_checked += len(pack.cv.skills)
    flagged.extend(check_skills(pack.cv.skills, corpus, skill_ratio))

    # 3. Cover letter: factual sentences must trace to the corpus, the research
    #    notes, or the job context.
    references = [item.text for item in corpus.items] + list(job_context or [])
    if research_notes:
        references.extend(_split_sentences(research_notes))
    sentences = _split_sentences(pack.cover_letter)
    for n, sentence in enumerate(sentences, start=1):
        if n == 1 or n == len(sentences):  # greeting / sign-off lines
            continue
        if not _looks_factual(sentence):
            continue
        claims_checked += 1
        best = _best_ratio(sentence, references)
        if best < letter_ratio:
            best = max(best, _best_pair_ratio(sentence, references))
        if best < letter_ratio:
            flagged.append(
                FlaggedClaim(
                    where=f"cover_letter:sentence:{n}",
                    text=sentence,
                    reason=f"factual claim not traceable to the corpus or research (best match {best:.2f})",
                    best_match_ratio=round(best, 3),
                )
            )

    return FabricationReport(
        flags=len(flagged),
        claims_checked=claims_checked,
        flagged=flagged,
        thresholds={"bullet": bullet_ratio, "skill": skill_ratio, "letter": letter_ratio},
    )

