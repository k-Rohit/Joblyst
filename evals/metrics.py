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


SCORED_FIELDS = (
    "seniority",
    "remote_ok",
    "years_experience",
    "primary_roles",
    "skills",
    "locations",
)
LIST_FIELDS = {"primary_roles", "skills", "locations"}
YEARS_TOLERANCE = 0.5  # extraction reads years off a CV; treat rounding as correct


def _normalize_set(values: list[str] | None) -> set[str]:
    return {str(v).strip().lower() for v in (values or []) if str(v).strip()}


def _field_score(field: str, expected: object, actual: object) -> float:
    """1.0/0.0 for scalars; F1 over the normalized sets for list fields."""
    if field in LIST_FIELDS:
        exp, act = _normalize_set(expected), _normalize_set(actual)  # type: ignore[arg-type]
        if not exp and not act:
            return 1.0
        if not exp or not act:
            return 0.0
        precision = len(exp & act) / len(act)
        recall = len(exp & act) / len(exp)
        return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)

    if field == "years_experience":
        if expected is None and actual is None:
            return 1.0
        if expected is None or actual is None:
            return 0.0
        return 1.0 if abs(float(expected) - float(actual)) <= YEARS_TOLERANCE else 0.0  # type: ignore[arg-type]

    if isinstance(expected, str) or isinstance(actual, str):
        return 1.0 if str(expected).strip().lower() == str(actual).strip().lower() else 0.0

    return 1.0 if expected == actual else 0.0


class ProfileFieldAccuracy(base_metric.BaseMetric):
    """Per-field accuracy of extract_profile against a human-verified expected Profile.

    ``projects`` is deliberately not scored — free text with no clean scoring
    function, and a known bug (see engineering_log.md) means the extractor
    doesn't reliably leave it empty; that's tracked separately, not here.
    """

    def __init__(self, name: str = "profile_field_accuracy") -> None:
        super().__init__(name=name)

    def score(self, expected: dict, new_profile: dict, **_: object) -> ScoreResult:
        per_field = {f: _field_score(f, expected.get(f), new_profile.get(f)) for f in SCORED_FIELDS}
        overall = sum(per_field.values()) / len(per_field)
        wrong = [f for f, v in per_field.items() if v < 1.0]
        return ScoreResult(
            name=self.name,
            value=overall,
            reason=f"off on: {wrong}" if wrong else "every scored field matched",
            metadata={"per_field": per_field},
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
