from unittest.mock import MagicMock, patch

from joblyst import runner
from joblyst.schemas.schemas import Profile


def test_run_search_starts_fresh():
    fake_invoke = MagicMock(return_value={})

    with patch.object(runner, "_invoke", fake_invoke):
        runner.run_search(Profile(name="Ananya"), "cv text", thread_id="t-1")

        what_was_sent = fake_invoke.call_args.args[0]

        assert what_was_sent["jobs"] == []
        assert what_was_sent["ranked_jobs"] == []
        assert what_was_sent["llm_calls"] == 0
        assert what_was_sent["reformulation_count"] == 0
        assert what_was_sent["external_job_text"] is None


def test_run_external_job_passes_profile_and_cv_text():
    profile = Profile(name="Rohit")
    fake_invoke = MagicMock(return_value={})

    with patch.object(runner, "_invoke", fake_invoke):
        runner.run_external_job(
            profile, "cv text", thread_id="t-1", external_job_text="Data Engineer job"
        )

        what_was_sent = fake_invoke.call_args.args[0]
        assert (
            what_was_sent["profile"] is profile
        )  # the exact object we passed, not just "something"
        assert what_was_sent["cv_text"] == "cv text"
        assert what_was_sent["external_job_text"] == "Data Engineer job"
