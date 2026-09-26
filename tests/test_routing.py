"""Routing tests for the two conditional edges in the graph.

Both routers are plain Python over the state — same input, same branch, every
time — so these are unit tests, not an eval: there is no model output to score.
They exist because a wrong branch is silent. Routing into ``tailor`` with a
stale ``selected_job_id`` or skipping reformulation on a thin result set both
produce a plausible-looking run with no error anywhere in the trace.

Boundary cases are pinned deliberately: the >= / < comparisons in
``should_reformulate`` are exactly where an off-by-one would hide.
"""

from __future__ import annotations

from langgraph.graph import END

from joblyst.graph.graph import (
    GOOD_FIT_THRESHOLD,
    MAX_REFFORMULATIONS,
    MIN_GOOD_JOBS,
    route_entry,
    should_reformulate,
)
from joblyst.schemas.schemas import JobPosting, RankedJob


def _ranked(score: int) -> RankedJob:
    """A RankedJob carrying nothing but the fit_score — the only field routing reads."""
    return RankedJob(
        job=JobPosting(
            job_id=f"job-{score}",
            title="Data Engineer",
            company="Acme",
            location="Pune, India",
            remote=False,
            description="",
            url="",
            source="cache",
        ),
        fit_score=score,
        fit_explanation="",
    )


class TestRouteEntry:
    def test_selected_job_routes_to_tailor(self):
        assert route_entry({"selected_job_id": "job-1"}) == "tailor"

    def test_external_job_text_routes_to_scorer(self):
        assert route_entry({"external_job_text": "We are hiring..."}) == "score_external_job"

    def test_empty_state_routes_to_search(self):
        assert route_entry({}) == "fetch_jobs"

    def test_explicit_tailor_wins_over_stray_external_text(self):
        # Both set: an explicit tailor request must win, or a tailoring run on a
        # thread that once scored a pasted job would silently re-score it instead.
        state = {"selected_job_id": "job-1", "external_job_text": "We are hiring..."}
        assert route_entry(state) == "tailor"

    def test_none_selected_job_routes_to_search(self):
        # run_search passes selected_job_id=None explicitly so a reused thread
        # never routes into tailoring against a stale id.
        assert route_entry({"selected_job_id": None}) == "fetch_jobs"

    def test_empty_string_selected_job_routes_to_search(self):
        assert route_entry({"selected_job_id": ""}) == "fetch_jobs"


class TestShouldReformulate:
    def test_no_jobs_reformulates(self):
        assert should_reformulate({}) == "reformulate_query"

    def test_too_few_good_jobs_reformulates(self):
        state = {"ranked_jobs": [_ranked(90)] * (MIN_GOOD_JOBS - 1), "reformulation_count": 0}
        assert should_reformulate(state) == "reformulate_query"

    def test_enough_good_jobs_ends(self):
        state = {"ranked_jobs": [_ranked(90)] * MIN_GOOD_JOBS, "reformulation_count": 0}
        assert should_reformulate(state) == END

    def test_score_exactly_at_threshold_counts_as_good(self):
        # The code uses >=, so a job scoring exactly 60 is a good match.
        state = {"ranked_jobs": [_ranked(GOOD_FIT_THRESHOLD)] * MIN_GOOD_JOBS, "reformulation_count": 0}
        assert should_reformulate(state) == END

    def test_score_one_below_threshold_does_not_count(self):
        state = {"ranked_jobs": [_ranked(GOOD_FIT_THRESHOLD - 1)] * MIN_GOOD_JOBS, "reformulation_count": 0}
        assert should_reformulate(state) == "reformulate_query"

    def test_reformulation_cap_stops_the_loop(self):
        # Still short on good jobs, but out of retries — must end, not loop forever.
        state = {"ranked_jobs": [], "reformulation_count": MAX_REFFORMULATIONS}
        assert should_reformulate(state) == END

    def test_one_below_the_cap_still_reformulates(self):
        state = {"ranked_jobs": [], "reformulation_count": MAX_REFFORMULATIONS - 1}
        assert should_reformulate(state) == "reformulate_query"

    def test_poor_jobs_do_not_satisfy_the_gate(self):
        # A run can return plenty of jobs and still be a bad result — the gate
        # counts GOOD jobs, not jobs.
        state = {"ranked_jobs": [_ranked(10)] * 25, "reformulation_count": 0}
        assert should_reformulate(state) == "reformulate_query"
