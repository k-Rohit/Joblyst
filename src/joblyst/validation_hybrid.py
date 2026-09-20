"""Two-stage fabrication checker: free deterministic pass, then a scoped LLM pass.

Stage 1 is the deterministic difflib check — the same code ``validation.py``
runs, so the two can never disagree on the part that is supposed to be
reproducible.

Stage 2 is a narrow LLM drift check that runs ONLY on claims that already
passed stage 1. Its question is deliberately small: stage 1 has already ruled
out wholesale invention, so all that's left is a single number, tool, or detail
swapped inside otherwise-faithful wording — which a similarity score
structurally cannot see (a 40%->60% edit is one character, scoring ~0.98).

What reaches stage 2, and what never does:

    experience bullets  stage 1 -> stage 2     prose, can be reworded
    project bullets     stage 1 -> stage 2     prose, can be reworded
    summary             stage 1 -> stage 2     prose, can be reworded
    cover letter        stage 1 -> stage 2     prose, can be reworded
    skills              stage 1 only           a vocabulary lookup, no judgment to make
    headline            stage 1 only           short and title-like, nothing to hide a detail in

Union-only, by construction: a stage-1 flag returns immediately and never
reaches stage 2, so a non-deterministic component can never suppress a
verifiable finding. Stage 2 only ever *adds*.

Stage-2 calls are issued concurrently with ``.batch()`` — one round trip's
latency for the whole pack instead of one per surviving claim — while staying
one focused prompt per claim, so per-item attention isn't diluted.
"""

from __future__ import annotations

from pydantic import BaseModel

from joblyst.config import get_settings
from joblyst.corpus import CandidateCorpus
from joblyst.llm import get_chat_model
from joblyst.prompts.drift_check import DRIFT_CHECK_PROMPT
from joblyst.schemas.schemas import FabricationReport, FlaggedClaim, TailoringPack
from joblyst.validation import (
    _best_pair_ratio,
    _best_ratio,
    _looks_factual,
    _ratio,
    _split_sentences,
    check_skills,
)

LLM_JUDGE_MODEL = "openai:gpt-4o-mini"

# How many of the closest real sources to hand the judge for a claim grounded
# by search (summary, cover letter) rather than by an explicit corpus_ref.
_TOP_SOURCES = 3


class _DriftCheck(BaseModel):
    """Structured-output target for one stage-2 check."""

    grounded: bool
    reason: str = ""


class _Survivor(BaseModel):
    """A claim that passed stage 1 and still warrants the semantic check."""

    where: str
    text: str
    sources: list[str]
    best_ratio: float


def _run_drift_checks(survivors: list[_Survivor]) -> list[FlaggedClaim]:
    """Check every survivor concurrently. Returns flags for the ungrounded ones.

    ``.batch()`` keeps one prompt per claim (so the judge stays focused on a
    single pair) but issues them in parallel, so a pack costs one round trip
    instead of one per claim. Output order matches input order.
    """
    if not survivors:
        return []

    model = get_chat_model(LLM_JUDGE_MODEL, temperature=0.0).with_structured_output(_DriftCheck)
    prompts = [
        DRIFT_CHECK_PROMPT.format(rewrite=s.text, sources="\n".join(f"- {src}" for src in s.sources))
        for s in survivors
    ]
    results: list[_DriftCheck] = model.batch(prompts)  # type: ignore[assignment]

    return [
        FlaggedClaim(
            where=survivor.where,
            text=survivor.text,
            reason=result.reason or "LLM judge found an ungrounded detail",
            stage="llm",
            best_match_ratio=round(survivor.best_ratio, 3),
        )
        for survivor, result in zip(survivors, results, strict=True)
        if not result.grounded
    ]


def _ground_by_search(text: str, references: list[str], threshold: float) -> float:
    """Best support for ``text`` anywhere in ``references``, for claims with no corpus_ref.

    Falls back to ``_best_pair_ratio`` because an honest summary or cover-letter
    sentence often assembles facts from two different corpus lines, and neither
    one alone would score well.
    """
    best = _best_ratio(text, references)
    if best < threshold:
        best = max(best, _best_pair_ratio(text, references))
    return best


def validate_pack_hybrid(
    pack: TailoringPack,
    corpus: CandidateCorpus,
    research_notes: str | None = None,
    job_context: list[str] | None = None,
) -> FabricationReport:
    """Deterministic pass over everything; LLM pass only where it earns its cost.

    ``job_context`` (e.g. job title and company) and ``research_notes`` join the
    reference pool for the summary and cover letter, so "I am applying for X at
    Y" or a researched company fact isn't wrongly flagged as ungrounded.
    """
    settings = get_settings()
    bullet_ratio, skill_ratio, letter_ratio = settings.fab_bullet_ratio, settings.fab_skill_ratio, settings.fab_letter_ratio
    flagged: list[FlaggedClaim] = []
    survivors: list[_Survivor] = []
    claims_checked = 0

    def check_bullet(bullet) -> None:
        """Stage 1 against the bullet's cited corpus item; queue it if it passes."""
        nonlocal claims_checked
        claims_checked += 1
        where = f"cv_bullet:{bullet.corpus_ref}"
        item = corpus.get(bullet.corpus_ref)
        if item is None:
            flagged.append(FlaggedClaim(where=where, text=bullet.text, reason="corpus_ref does not resolve to any corpus item"))
            return
        ratio = _ratio(bullet.text, item.text)
        if ratio < bullet_ratio:
            flagged.append(
                FlaggedClaim(
                    where=where,
                    text=bullet.text,
                    reason=f"rewrite drifted too far from its corpus item (ratio {ratio:.2f} < {bullet_ratio})",
                    best_match_ratio=round(ratio, 3),
                )
            )
            return
        survivors.append(_Survivor(where=where, text=bullet.text, sources=[item.text], best_ratio=ratio))

    def check_prose(where: str, text: str, references: list[str], threshold: float, *, use_llm: bool) -> None:
        """Stage 1 by searching all references; queue for stage 2 only if allowed."""
        nonlocal claims_checked
        claims_checked += 1
        best = _ground_by_search(text, references, threshold)
        if best < threshold:
            flagged.append(
                FlaggedClaim(
                    where=where,
                    text=text,
                    reason=f"factual claim not traceable to the corpus (best match {best:.2f})",
                    best_match_ratio=round(best, 3),
                )
            )
            return
        if use_llm:
            top = sorted(references, key=lambda ref: _ratio(text, ref), reverse=True)[:_TOP_SOURCES]
            survivors.append(_Survivor(where=where, text=text, sources=top, best_ratio=best))

    # 1. Bullets — each cites one corpus item, so stage 1 compares against it directly.
    for entry in pack.cv.experience:
        for bullet in entry.bullets:
            check_bullet(bullet)
    for entry in pack.cv.project:
        for bullet in entry.project_bullets:
            check_bullet(bullet)

    # 2. Skills — deterministic only, shared with validate_pack so the two agree.
    claims_checked += len(pack.cv.skills)
    flagged.extend(check_skills(pack.cv.skills, corpus, skill_ratio))

    # 3. Headline and summary — no corpus_ref, so both ground by searching the
    #    corpus. Only the summary is prose long enough to hide a swapped detail.
    references = [item.text for item in corpus.items] + list(job_context or [])
    if research_notes:
        references.extend(_split_sentences(research_notes))

    if pack.cv.headline.strip():
        check_prose("headline", pack.cv.headline, references, letter_ratio, use_llm=False)
    for n, sentence in enumerate(_split_sentences(pack.cv.summary), start=1):
        if _looks_factual(sentence):
            check_prose(f"summary:sentence:{n}", sentence, references, letter_ratio, use_llm=True)

    # 4. Cover letter — greeting and sign-off carry no checkable claim.
    sentences = _split_sentences(pack.cover_letter)
    for n, sentence in enumerate(sentences, start=1):
        if n == 1 or n == len(sentences) or not _looks_factual(sentence):
            continue
        check_prose(f"cover_letter:sentence:{n}", sentence, references, letter_ratio, use_llm=True)

    # Stage 2 — every survivor across the whole pack, in one concurrent burst.
    flagged.extend(_run_drift_checks(survivors))

    return FabricationReport(
        flags=len(flagged),
        claims_checked=claims_checked,
        flagged=flagged,
        thresholds={"bullet": bullet_ratio, "skill": skill_ratio, "letter": letter_ratio},
    )
