"""Tests for the two query guards in fetch_jobs.

Both exist because the prompt is a request, not a guarantee: the model can still
hand back a list of roles or a title trailing off into skills. Boards match a
query against one job TITLE literally, so either shape returns nothing and the
run looks merely unlucky rather than broken.

The separator-before-word-count ordering is pinned deliberately — reversing it is
what shipped the 'Data Analyst OR Business Analyst OR' query (engineering_log.md).
"""

from __future__ import annotations

from joblyst.graph.nodes.fetch_jobs import MAX_QUERY_WORDS, _fallback_query, _trim_query
from joblyst.schemas.schemas import Profile


class TestTrimQuery:
    def test_clean_title_is_untouched(self):
        assert _trim_query("lead data engineer") == ("lead data engineer", "")

    def test_the_query_that_shipped(self):
        # Verbatim from a baseline-batch trace. Word-cutting this to 6 words left
        # a trailing "OR" and matched no posting at all.
        kept, dropped = _trim_query("Data Analyst OR Business Analyst OR Analytics Intern")
        assert kept == "Data Analyst"
        assert "OR" not in kept
        assert dropped == "Business Analyst Analytics Intern"

    def test_or_list_keeps_first_role(self):
        assert _trim_query("data analyst OR business analyst")[0] == "data analyst"

    def test_comma_list_keeps_first_role(self):
        assert _trim_query("data engineer, data scientist")[0] == "data engineer"

    def test_pipe_and_semicolon_are_separators(self):
        assert _trim_query("data engineer | data scientist")[0] == "data engineer"
        assert _trim_query("data engineer; data scientist")[0] == "data engineer"

    def test_slash_survives_as_one_title(self):
        # "AI/ML engineer" is a real posting title, not a list.
        assert _trim_query("AI/ML engineer") == ("AI/ML engineer", "")

    def test_ampersand_survives_as_one_title(self):
        assert _trim_query("R&D engineer") == ("R&D engineer", "")

    def test_skill_tail_is_still_cut_by_word_count(self):
        kept, dropped = _trim_query("senior data scientist AI engineer deep learning LLMs RAG")
        assert len(kept.split()) == MAX_QUERY_WORDS
        assert dropped

    def test_no_separator_output_ever_ends_on_a_separator(self):
        # The actual defect was a query ENDING in a separator. Guard the class,
        # not just the one string that shipped.
        for query in (
            "Data Analyst OR Business Analyst OR Analytics Intern",
            "a OR b OR c OR d OR e OR f OR g",
            "one, two, three, four, five, six, seven",
        ):
            kept, _ = _trim_query(query)
            last = kept.split()[-1].lower()
            assert last not in {"or", "and"}
            assert not kept.rstrip().endswith((",", ";", "|"))


class TestFallbackQuery:
    def test_uses_one_role_not_two(self):
        # Joining two roles produced "data analyst business analyst" — the same
        # unsearchable list the prompt now forbids.
        profile = Profile(primary_roles=["data analyst", "business analyst", "analytics intern"])
        assert _fallback_query(profile) == "data analyst"

    def test_falls_back_to_skills_when_no_roles(self):
        profile = Profile(skills=["python", "sql", "dbt", "airflow"])
        assert _fallback_query(profile) == "python sql dbt"

    def test_empty_profile_yields_empty_query(self):
        # Empty is correct here: run_search's caller decides what to do, and an
        # invented query would search for something the candidate never claimed.
        assert _fallback_query(Profile()) == ""


class TestReformulatedQueryIsTrimmed:
    """The reformulate node must not hand fetch_jobs a list.

    fetch_jobs puts ``search_query`` into its prompt verbatim as guidance, and the
    model then issues one tool call per term in it — a 16-term OR list became 16
    searches in one run. The node now applies the same guard as the fetch path.
    """

    def test_reformulated_list_is_cut_to_one_title(self):
        # Verbatim from reformulate_query before the prompt was constrained.
        raw = (
            "Data Analyst OR Business Analyst OR Analytics OR Data Scientist OR "
            "Data Specialist OR Reporting Analyst OR SQL OR Excel OR Looker OR Python"
        )
        kept, dropped = _trim_query(raw)
        assert kept == "Data Analyst"
        assert dropped  # the rest is recorded, not silently discarded

    def test_a_clean_reformulation_passes_through(self):
        assert _trim_query("business intelligence analyst") == ("business intelligence analyst", "")
