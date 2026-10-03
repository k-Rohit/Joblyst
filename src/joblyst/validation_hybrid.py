"""Fabrication checker: exact lookup for skills, an LLM judge for all prose.

    skills              deterministic only    a vocabulary lookup — no judgment to make
    experience bullets  LLM judge             prose, can be honestly reworded
    project bullets     LLM judge
    summary             LLM judge
    cover letter        LLM judge
    headline            LLM judge

Prose used to pass a difflib similarity gate first, and anything under the
threshold was flagged without the judge seeing it. That gate cannot tell
direction: honest summarisation scores low exactly like invention does. On the
14-case tailoring batch it produced 74 of 90 flags, nearly all on faithful
summaries ("...retrained monthly on 1.2M records" shortened away scored 0.645
and was flagged). So similarity no longer decides anything for prose — it is
only used to pick which CV lines to show the judge as the source.

Two checks stay deterministic because they are facts, not judgments: a skill
either is or is not in the CV's vocabulary, and a bullet either cites a corpus
item that exists or it does not.

Judge calls run concurrently (capped — see JUDGE_MAX_CONCURRENCY) with one
focused prompt per claim.
"""

from __future__ import annotations

from pydantic import BaseModel

from joblyst.config import get_settings
from joblyst.corpus import CandidateCorpus
from joblyst.llm import get_chat_model
from joblyst.prompts.drift_check import DRIFT_CHECK_PROMPT
from joblyst.schemas.schemas import FabricationReport, FlaggedClaim, TailoringPack
from joblyst.validation import (
    _looks_factual,
    _ratio,
    _split_sentences,
    check_skills,
)

JUDGE_MAX_CONCURRENCY = 3
JUDGE_MAX_ATTEMPTS = 8

# How many of the closest real sources to hand the judge for a claim with no
# corpus_ref (headline, summary, cover letter). Three lets a sentence that
# combines two CV facts still have both in front of the judge.
_TOP_SOURCES = 3


class _DriftCheck(BaseModel):
    """Structured-output target for one judge call."""

    grounded: bool
    reason: str = ""


class _Survivor(BaseModel):
    """A prose claim queued for the judge, with the CV lines it should be compared to."""

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

    # The judge model has a low tokens-per-minute limit (gpt-4.1: 30k on this
    # account) and each few-shot judge call is ~640 tokens, so firing every claim
    # at once returns 429 — and since this runs inside the graph, an unhandled 429
    # fails the whole tailoring run. Cap the parallelism and retry with backoff.
    model = (
        get_chat_model(get_settings().joblyst_judge_model, temperature=0.0)
        .with_structured_output(_DriftCheck)
        .with_retry(stop_after_attempt=JUDGE_MAX_ATTEMPTS, wait_exponential_jitter=True)
    )
    prompts = [
        DRIFT_CHECK_PROMPT.format(rewrite=s.text, sources="\n".join(f"- {src}" for src in s.sources))
        for s in survivors
    ]
    results: list[_DriftCheck] = model.batch(prompts, config={"max_concurrency": JUDGE_MAX_CONCURRENCY})  # type: ignore[assignment]

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


def _closest_sources(text: str, references: list[str]) -> tuple[list[str], float]:
    """The CV lines most similar to ``text`` — used to choose what the judge sees, not to judge."""
    ranked = sorted(references, key=lambda ref: _ratio(text, ref), reverse=True)[:_TOP_SOURCES]
    best = _ratio(text, ranked[0]) if ranked else 0.0
    return ranked, best


def validate_pack_hybrid(
    pack: TailoringPack,
    corpus: CandidateCorpus,
    research_notes: str | None = None,
    job_context: list[str] | None = None,
) -> FabricationReport:
    """Skills by exact lookup; every prose claim by the LLM judge.

    ``job_context`` (e.g. job title and company) and ``research_notes`` join the
    reference pool for the headline, summary and cover letter, so "I am applying
    for X at Y" or a researched company fact isn't wrongly flagged.
    """
    settings = get_settings()
    skill_ratio = settings.fab_skill_ratio
    flagged: list[FlaggedClaim] = []
    queued: list[_Survivor] = []
    claims_checked = 0

    def queue_bullet(bullet) -> None:
        """A bullet is judged against the one corpus item it cites."""
        nonlocal claims_checked
        claims_checked += 1
        where = f"cv_bullet:{bullet.corpus_ref}"
        item = corpus.get(bullet.corpus_ref)
        if item is None:
            # A citation that points at nothing is a fact, not a judgment call.
            flagged.append(FlaggedClaim(where=where, text=bullet.text, reason="corpus_ref does not resolve to any corpus item"))
            return
        queued.append(_Survivor(where=where, text=bullet.text, sources=[item.text], best_ratio=_ratio(bullet.text, item.text)))

    def queue_prose(where: str, text: str, references: list[str]) -> None:
        """Uncited prose is judged against its closest CV lines."""
        nonlocal claims_checked
        claims_checked += 1
        sources, best = _closest_sources(text, references)
        queued.append(_Survivor(where=where, text=text, sources=sources, best_ratio=best))

    # 1. Bullets — each cites one corpus item.
    for entry in pack.cv.experience:
        for bullet in entry.bullets:
            queue_bullet(bullet)
    for entry in pack.cv.project:
        for bullet in entry.project_bullets:
            queue_bullet(bullet)

    # 2. Skills — the only deterministic check, shared with validate_pack so the two agree.
    claims_checked += len(pack.cv.skills)
    flagged.extend(check_skills(pack.cv.skills, corpus, skill_ratio))

    # 3. Headline, summary and cover letter — no citation, so compared to the closest CV lines.
    references = [item.text for item in corpus.items] + list(job_context or [])
    if research_notes:
        references.extend(_split_sentences(research_notes))

    if pack.cv.headline.strip():
        queue_prose("headline", pack.cv.headline, references)
    for n, sentence in enumerate(_split_sentences(pack.cv.summary), start=1):
        if _looks_factual(sentence):
            queue_prose(f"summary:sentence:{n}", sentence, references)

    # Greeting and sign-off carry no checkable claim.
    sentences = _split_sentences(pack.cover_letter)
    for n, sentence in enumerate(sentences, start=1):
        if n == 1 or n == len(sentences) or not _looks_factual(sentence):
            continue
        queue_prose(f"cover_letter:sentence:{n}", sentence, references)

    # Every prose claim across the whole pack, judged in one concurrent burst.
    flagged.extend(_run_drift_checks(queued))

    return FabricationReport(
        flags=len(flagged),
        claims_checked=claims_checked,
        flagged=flagged,
        thresholds={"skill": skill_ratio},
    )
