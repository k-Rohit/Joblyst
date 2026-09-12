"""LLM-as-judge fabrication checker — an experiment to compare against
``validation.py``'s deterministic approach, not a replacement for it.

Same input/output shape as ``validate_pack`` (takes a TailoringPack + corpus,
returns a FabricationReport) so the two can be run side by side on the exact
same test case and compared directly.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from joblyst.config import get_settings
from joblyst.corpus import CandidateCorpus
from joblyst.llm import get_chat_model
from joblyst.schemas.schemas import FabricationReport, FlaggedClaim, TailoringPack
from joblyst.validation import _best_ratio, _looks_factual, _ratio, _split_sentences

LLM_JUDGE_MODEL = "openai:gpt-4o-mini"

# Stage 2 only checks for drift WITHIN an already-similar pair — it assumes
# stage 1 already ruled out wholesale fabrication, so the question is narrow
# on purpose: don't re-litigate overall similarity, just look for one changed
# number, tool, or detail that a high ratio score can hide.
_DRIFT_PROMPT = """A rewritten claim and its real source(s) are given below. The rewrite already \
scored as similar overall — your only job is to check for one specific kind of problem a \
similarity score can miss: a number, tool, or detail that was changed or added, hidden inside \
otherwise-faithful wording.

Rewrite:
{rewrite}

Real source(s):
{sources}

If every number, tool, and detail in the rewrite is actually present in the source(s), it's grounded. \
If anything was changed (e.g. a bigger number) or added (e.g. a tool never mentioned), it's not.
"""

_JUDGE_PROMPT = """You are a fact-checker. Below is a candidate's real corpus (their actual CV, \
one item per line with an id) and a tailored CV + cover letter generated for a job application.

Check EVERY claim in the tailored content against the corpus:
- Every CV bullet: does its corpus_ref resolve to a real item, and does the rewrite honestly \
represent that item (no invented tools, metrics, dates, or employers)?
- Every skill: is it actually present in the corpus (or a strict subset of a corpus skill, \
e.g. claiming "AWS" when the corpus says "basic AWS" is honest)?
- Every factual-sounding cover letter sentence (one with a number or a named product/company/tool): \
can it be traced to the corpus?

Flag ONLY claims that are NOT grounded in the corpus. For each flagged claim, give:
- where: e.g. "cv_bullet:<corpus_ref>", "skill:<name>", "cover_letter:sentence:<n>"
- text: the flagged text itself
- reason: a short, specific explanation of what's wrong

Do not flag anything you can find real support for in the corpus, even if reworded.

Candidate corpus:
{corpus}

Tailored CV (JSON):
{cv_json}

Cover letter:
{cover_letter}
"""


class _JudgeFlags(BaseModel):
    """Structured-output target for the judge call — just the flags."""

    flagged: list[FlaggedClaim] = Field(default_factory=list)


def _count_claims(pack: TailoringPack) -> int:
    """Count claims the same way ``validate_pack`` does, so ``claims_checked`` is comparable."""
    n = sum(len(entry.bullets) for entry in pack.cv.experience)
    n += sum(len(entry.project_bullets) for entry in pack.cv.project)
    n += len(pack.cv.skills)
    sentences = _split_sentences(pack.cover_letter)
    n += sum(1 for i, s in enumerate(sentences, 1) if i not in (1, len(sentences)) and _looks_factual(s))
    return n


def validate_pack_llm(pack: TailoringPack, corpus: CandidateCorpus) -> FabricationReport:
    """LLM-judge version of ``validate_pack``. Non-deterministic; for comparison only."""
    model = get_chat_model(LLM_JUDGE_MODEL, temperature=0.0).with_structured_output(_JudgeFlags)
    prompt = _JUDGE_PROMPT.format(
        corpus=corpus.render_for_prompt(),
        cv_json=pack.cv.model_dump_json(indent=2),
        cover_letter=pack.cover_letter,
    )
    result: _JudgeFlags = model.invoke(prompt)  # type: ignore

    return FabricationReport(
        flags=len(result.flagged),
        claims_checked=_count_claims(pack),
        flagged=result.flagged,
        thresholds={},  # no numeric knobs for a judgment call
    )


class _DriftCheck(BaseModel):
    """Structured-output target for one stage-2 pairwise check."""

    grounded: bool
    reason: str = ""


def _check_drift(text: str, sources: list[str]) -> str | None:
    """Ask the LLM if ``text`` changed/added a detail vs. ``sources``. None = grounded."""
    model = get_chat_model(LLM_JUDGE_MODEL, temperature=0.0).with_structured_output(_DriftCheck)
    prompt = _DRIFT_PROMPT.format(rewrite=text, sources="\n".join(f"- {s}" for s in sources))
    result: _DriftCheck = model.invoke(prompt)  # type: ignore
    return None if result.grounded else (result.reason or "LLM judge found an ungrounded detail")


def _check_bullet_hybrid(bullet, corpus: CandidateCorpus, bullet_ratio: float) -> FlaggedClaim | None:
    """Stage 1 (free) then, only if stage 1 passes, stage 2 (LLM) for one bullet."""
    item = corpus.get(bullet.corpus_ref)
    if item is None:
        return FlaggedClaim(where=f"cv_bullet:{bullet.corpus_ref}", text=bullet.text, reason="corpus_ref does not resolve to any corpus item")

    ratio = _ratio(bullet.text, item.text)
    if ratio < bullet_ratio:
        # Stage 1 already caught this — no need to spend an LLM call confirming it.
        return FlaggedClaim(
            where=f"cv_bullet:{bullet.corpus_ref}",
            text=bullet.text,
            reason=f"rewrite drifted too far from its corpus item (ratio {ratio:.2f} < {bullet_ratio})",
            best_match_ratio=round(ratio, 3),
        )

    # Stage 1 passed — check the one thing ratio can't see: a swapped detail.
    drift_reason = _check_drift(bullet.text, [item.text])
    if drift_reason:
        return FlaggedClaim(where=f"cv_bullet:{bullet.corpus_ref}", text=bullet.text, reason=drift_reason, best_match_ratio=round(ratio, 3))
    return None


def validate_pack_hybrid(pack: TailoringPack, corpus: CandidateCorpus) -> FabricationReport:
    """Deterministic first pass everywhere; LLM second pass only where it earns its cost.

    Skills stay deterministic-only (a vocabulary match needs no judgment call).
    Bullets and cover-letter sentences that pass the free ratio check still go
    through one scoped LLM comparison, since a high ratio can hide a single
    changed number or invented tool (see the four-case comparison this is
    built from — the ratio check missed all of them, the LLM caught all of them).
    """
    settings = get_settings()
    bullet_ratio, skill_ratio, letter_ratio = settings.fab_bullet_ratio, settings.fab_skill_ratio, settings.fab_letter_ratio
    flagged: list[FlaggedClaim] = []
    claims_checked = 0

    # 1. Bullets — hybrid check, both experience and project sections.
    for entry in pack.cv.experience:
        for bullet in entry.bullets:
            claims_checked += 1
            result = _check_bullet_hybrid(bullet, corpus, bullet_ratio)
            if result:
                flagged.append(result)
    for entry in pack.cv.project:
        for bullet in entry.project_bullets:
            claims_checked += 1
            result = _check_bullet_hybrid(bullet, corpus, bullet_ratio)
            if result:
                flagged.append(result)

    # 2. Skills — deterministic only, unchanged from validate_pack.
    corpus_skills = corpus.skills()
    for skill in pack.cv.skills:
        claims_checked += 1
        best = _best_ratio(skill, corpus_skills) if corpus_skills else 0.0
        if best < skill_ratio:
            flagged.append(
                FlaggedClaim(where=f"skill:{skill}", text=skill, reason=f"skill is not in the candidate's corpus (best match {best:.2f})", best_match_ratio=round(best, 3))
            )

    # 3. Cover letter — hybrid, same shape as bullets: free check first, LLM
    #    only for sentences that already look close enough to be worth a closer read.
    references = [item.text for item in corpus.items]
    sentences = _split_sentences(pack.cover_letter)
    for n, sentence in enumerate(sentences, start=1):
        if n == 1 or n == len(sentences) or not _looks_factual(sentence):
            continue
        claims_checked += 1
        best = _best_ratio(sentence, references)
        if best < letter_ratio:
            flagged.append(
                FlaggedClaim(where=f"cover_letter:sentence:{n}", text=sentence, reason=f"factual claim not traceable to the corpus (best match {best:.2f})", best_match_ratio=round(best, 3))
            )
            continue
        # Passed the free check — give the LLM the closest real matches to check against.
        top = sorted(references, key=lambda r: _ratio(sentence, r), reverse=True)[:3]
        drift_reason = _check_drift(sentence, top)
        if drift_reason:
            flagged.append(FlaggedClaim(where=f"cover_letter:sentence:{n}", text=sentence, reason=drift_reason, best_match_ratio=round(best, 3)))

    return FabricationReport(
        flags=len(flagged),
        claims_checked=claims_checked,
        flagged=flagged,
        thresholds={"bullet": bullet_ratio, "skill": skill_ratio, "letter": letter_ratio, "llm_check": 1.0},
    )
