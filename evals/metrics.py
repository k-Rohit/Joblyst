"""Deterministic metrics for the ranking eval — no LLM, so they are free and reproducible.

Opik hands each metric the dataset item's fields plus the task's output keys, so the
task returns ``new_*`` keys to avoid colliding with the logged ``fit_score`` / ``matched_skills``.
"""

from __future__ import annotations

from opik.evaluation.metrics import base_metric
from opik.evaluation.metrics.score_result import ScoreResult

GOOD_FIT_THRESHOLD = 60


def human_says_good(old_score: int, fit_ok: str) -> bool:
    """Turn the human verdict on the logged score into the side of 60 it should be on.

    fit_ok = yes  -> the old score was reasonable, so its side of 60 was right.
    fit_ok = no   -> the old score was wrong, so the right side is the opposite one.
    """
    old_good = old_score >= GOOD_FIT_THRESHOLD
    return old_good if fit_ok.strip().lower() == "yes" else not old_good


class SkillsInProfile(base_metric.BaseMetric):
    """1.0 when every skill the ranker claims as matched is really in the candidate's profile."""

    def __init__(self, name: str = "skills_in_profile") -> None:
        super().__init__(name=name)

    def score(self, new_matched_skills: list[str], profile: dict, **_: object) -> ScoreResult:
        known = {s.lower() for s in profile.get("skills", [])}
        projects = " ".join(profile.get("projects", [])).lower()
        invented = [s for s in new_matched_skills if s.lower() not in known and s.lower() not in projects]
        return ScoreResult(
            name=self.name,
            value=0.0 if invented else 1.0,
            reason=f"not in profile: {invented}" if invented else "all matched skills are in the profile",
        )


class ScoreOnRightSide(base_metric.BaseMetric):
    """1.0 when the new score lands on the side of 60 the human's label says it should."""

    def __init__(self, name: str = "score_on_right_side") -> None:
        super().__init__(name=name)

    def score(self, new_fit_score: int, fit_score: int, fit_ok: str, **_: object) -> ScoreResult:
        want_good = human_says_good(fit_score, fit_ok)
        got_good = new_fit_score >= GOOD_FIT_THRESHOLD
        return ScoreResult(
            name=self.name,
            value=1.0 if want_good == got_good else 0.0,
            reason=f"new score {new_fit_score}; human says {'good' if want_good else 'poor'} fit",
        )
