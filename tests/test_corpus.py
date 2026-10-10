from joblyst.corpus import build_corpus

CV = """SUMMARY
Data engineer building pipelines.

EXPERIENCE
Data Engineer, Philips, Chennai Nov'25 - Present
- Automated SQL transformations, cutting runtime from 1 hour to 15 minutes.
Machine Learning Engineer, Brightlane, Bengaluru (2018 - 2021)
- Built a feature store.
Serving Recommendations at Low Latency - PyData India (2023)

PROJECTS
Joblyst (2025 - Present)
- Job search agent.

CERTIFICATIONS
Google Data Analytics Professional Certificate (2024)
"""


def test_work_history_keeps_only_role_headings():
    # Roles have a date range; the talk and certificate have one year, and the
    # project is not work experience.
    assert build_corpus(CV).work_history() == [
        "Data Engineer, Philips, Chennai Nov'25 - Present",
        "Machine Learning Engineer, Brightlane, Bengaluru (2018 - 2021)",
    ]
