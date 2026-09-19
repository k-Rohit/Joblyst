"""Generate the synthetic fixture CVs used by the baseline batch.

Five fictional personas, all English CVs, all based in India — Joblyst's own
search scope is India-only (see DEFAULT_COUNTRY in search_job.py, the Jooble
base URL pinned to in.jooble.org, and cached_jobs.json built country="in"
only), so a fixture candidate based in London or Austin would exercise a
search path the real app never runs.

They differ on two axes on purpose:

  1. CANDIDATE   seniority, domain and location, so ranking produces a real
                 spread of fit scores instead of a cluster.
  2. STRUCTURE   heading style, skill formatting and bullet markers, because
                 corpus.py segments CVs with a line/keyword heuristic — the
                 fixtures have to exercise its edges, not just the happy path.

  junior_ds_in       ALL-CAPS headings, comma-separated skills, "-" bullets
  senior_mle_in      Title Case headings, "Category: a, b" skill lines
  career_changer_in  "TECHNICAL PROFICIENCIES" (an unrecognized skills heading),
                     projects-heavy with almost no professional experience
  lead_in_remote     "TECH STACK" heading, long bullets that wrap across lines
  mid_analyst_in     no summary at all, education before experience, one skill
                     per line

Each runs to roughly the length of a real two-page CV, with several roles,
four to six bullets per role, and the trailing sections real resumes carry
(certifications, projects, publications, achievements) — a thin fixture would
make both corpus segmentation and tailoring look easier than they are.

Run:  uv run python scripts/generate_fixture_cvs.py

Names, employers and contact details are invented.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fpdf import FPDF

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "fixture_cvs"

# fpdf2 stamps a creation date; pin it so regenerating doesn't churn git diffs.
_PIN_DATE = datetime(2026, 1, 1, tzinfo=UTC)


def _render(name: str, contact: str, sections: list[tuple[str, list[str]]], filename: str) -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_title("CV")
    width = pdf.epw

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(width, 9, name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(width, 5, contact, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    for heading, lines in sections:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(width, 7, heading, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9.5)
        for line in lines:
            # multi_cell defaults to new_x=RIGHT/new_y=TOP, which leaves the cursor
            # at the right edge on the SAME line — every following line then drifts
            # right and overlaps. Force a normal newline at the left margin.
            pdf.multi_cell(width, 4.6, line, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.5)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / filename
    pdf.creation_date = _PIN_DATE  # type: ignore[attr-defined]
    pdf.output(str(path))
    print(f"wrote {path.relative_to(OUT_DIR.parent.parent)}  ({pdf.pages_count} page(s))")


def junior_ds_in() -> None:
    _render(
        "Ananya Rao",
        "Bengaluru, India  |  ananya.rao@example.com  |  +91 98450 12233  |  Open to hybrid",
        [
            ("SUMMARY", [
                ("Data scientist with 2 years of experience building predictive models and self serve "
                "reporting for a consumer subscription product. Comfortable owning a problem end to end, "
                "from pulling the data in SQL through to presenting results to product managers. Looking "
                "for a role with more depth in production machine learning."),
            ]),
            ("SKILLS", [
                ("Python, SQL, pandas, NumPy, scikit-learn, statsmodels, Tableau, Looker, Git, "
                "Jupyter, Airflow, dbt, A/B testing, experimental design, regression analysis"),
            ]),
            ("EXPERIENCE", [
                "Junior Data Scientist, Northwind Analytics, Bengaluru (2024 - Present)",
                ("- Built a churn prediction model in scikit-learn that improved retention campaign "
                "targeting by 12% and is now retrained monthly on 1.2M subscriber records."),
                ("- Wrote and maintained 14 SQL transformation models in dbt feeding three executive "
                "Tableau dashboards reviewed weekly by the leadership team."),
                ("- Designed and analysed 8 A/B tests on onboarding flows, including power analysis and "
                "sample size calculations, and presented results to product managers."),
                ("- Reduced a nightly reporting job from 40 minutes to 9 minutes by rewriting three "
                "correlated subqueries as window functions."),
                ("- Built an anomaly alert in Python that flags unexpected signup drops, catching two "
                "payment integration outages before support tickets arrived."),
                "- Mentored one summer intern through their first production dashboard.",
                "Data Science Intern, Northwind Analytics, Bengaluru (2023 - 2024)",
                ("- Cleaned and validated a 400,000 row customer dataset, documenting 11 recurring data "
                "quality issues that were later fixed upstream."),
                "- Built the company's first cohort retention report, still used by the growth team.",
                "- Automated a weekly KPI email that had previously been assembled by hand in Excel.",
                "Undergraduate Research Assistant, St. Xavier's College Statistics Department (2022 - 2023)",
                "- Ran simulation studies in R comparing three variance estimation methods.",
                "- Co-authored a poster presented at the departmental research symposium.",
            ]),
            ("PROJECTS", [
                ("Transit Delay Predictor - Trained a gradient boosting model on two years of public "
                "transit data to predict bus arrival delays, deployed as a small Flask API."),
                ("Grocery Price Tracker - Built a scheduled Python scraper and Streamlit dashboard "
                "tracking price changes across 200 supermarket items."),
            ]),
            ("EDUCATION", [
                "BSc Statistics, St. Xavier's College, Mumbai (2023)",
                ("Relevant coursework: statistical learning, Bayesian inference, linear models, "
                "database systems. GPA 3.7."),
            ]),
            ("CERTIFICATIONS", [
                "Google Data Analytics Professional Certificate (2023)",
                "Tableau Desktop Specialist (2024)",
            ]),
        ],
        "junior_ds_in.pdf",
    )


def senior_mle_in() -> None:
    _render(
        "Arjun Mehta",
        "Hyderabad, India  |  arjun.mehta@example.com  |  +91 90080 45566",
        [
            ("Professional Summary", [
                ("Senior machine learning engineer with 8 years of experience taking models from research "
                "notebooks into production systems serving millions of requests per day. Specialised in "
                "recommendation and ranking systems, with deep experience in distributed training and "
                "model serving infrastructure. Has led teams of up to 6 engineers and owns hiring, "
                "technical direction and on call practice for the ML platform."),
            ]),
            ("Technical Skills", [
                "Languages: Python, Go, SQL, Scala",
                "Machine Learning: PyTorch, TensorFlow, scikit-learn, XGBoost, Hugging Face Transformers",
                "MLOps: MLflow, Weights and Biases, Kubeflow, Feast, ONNX",
                "Infrastructure: Kubernetes, Docker, AWS, Terraform, Airflow, Kafka, Redis",
                "Practices: distributed training, A/B testing, model monitoring, feature stores",
            ]),
            ("Work Experience", [
                "Senior Machine Learning Engineer, Halcyon Data, Hyderabad (2021 - Present)",
                ("- Led a team of 5 engineers delivering a real-time recommendation service handling "
                "40M requests per day at a p99 latency of 45ms."),
                ("- Cut model training time from 14 hours to 3 hours by moving to distributed PyTorch "
                "on Kubernetes with mixed precision."),
                ("- Introduced MLflow experiment tracking across 4 teams, replacing an ad hoc mix of "
                "spreadsheets and notebook outputs."),
                ("- Designed the feature store that now backs 9 production models, cutting the time to "
                "ship a new model from 6 weeks to 8 days."),
                "- Ran the migration of 23 models to ONNX runtime, reducing inference cost by 31%.",
                "- Chairs the weekly model review where every production change is signed off.",
                "Machine Learning Engineer, Brightlane, Bengaluru (2018 - 2021)",
                ("- Deployed 11 models to production and owned their monitoring, alerting and "
                "retraining schedules."),
                "- Reduced feature pipeline runtime from 9 hours to 2 hours using Airflow and Spark.",
                ("- Built an automated drift detection service that paged on distribution shift, "
                "catching a broken upstream feed within 20 minutes."),
                ("- Introduced shadow deployments so new models could be validated on live traffic "
                "before taking any real requests."),
                "- Interviewed 40+ candidates and helped grow the team from 3 to 9 engineers.",
                "Data Scientist, Meridian Retail Group, Pune (2017 - 2018)",
                ("- Built demand forecasting models for 1,400 stores, improving stock allocation "
                "accuracy by 9%."),
                "- Automated a pricing analysis that had taken two analysts three days each month.",
                "- Presented quarterly findings to the commercial director and regional managers.",
            ]),
            ("Selected Talks and Publications", [
                "Serving Recommendations at Low Latency - PyData India (2023)",
                "Feature Stores in Practice: What We Got Wrong - MLOps Community meetup (2022)",
                "Co-author, Scalable Ranking for Sparse Catalogues, industry workshop paper (2021)",
            ]),
            ("Education", [
                "M.Tech Computer Science, IIT Hyderabad (2017), Distinction",
                "B.Tech Mathematics and Computing, NIT Warangal (2015), First Class Honours",
            ]),
            ("Certifications", [
                "AWS Certified Machine Learning - Specialty (2022)",
                "Certified Kubernetes Application Developer (2021)",
            ]),
        ],
        "senior_mle_in.pdf",
    )


def career_changer_in() -> None:
    _render(
        "Priya Nair",
        "Bengaluru, India  |  priya.nair@example.com  |  +91 80 4123 7788  |  Open to remote",
        [
            ("OBJECTIVE", [
                ("Secondary school mathematics teacher of 11 years moving into data analytics. Self "
                "taught in Python and SQL over the past two years, with four analytics projects built "
                "for my own school and now in daily use by staff. Seeking an entry level analyst role "
                "where a strong statistics background and a track record of explaining numbers to non "
                "technical audiences are useful from day one."),
            ]),
            ("TECHNICAL PROFICIENCIES", [
                "Python, SQL, Excel, Power BI, pandas, matplotlib, Google Sheets, Jupyter",
            ]),
            ("PROJECTS", [
                ("Student Performance Dashboard - Built a Power BI dashboard tracking results for 600 "
                "students across 4 academic years, broken down by subject, teacher and cohort. Adopted "
                "by the school leadership team and reviewed at every termly staff meeting."),
                ("Attendance Predictor - Trained a logistic regression model in Python that flags "
                "students at risk of dropping out, using 5 years of historical attendance records. "
                "Identified 23 at risk students in its first term, 19 of whom were correctly flagged."),
                ("Timetable Optimiser - Wrote a Python script using constraint solving to generate the "
                "school timetable, replacing a manual process that took two staff a full week."),
                ("Exam Question Analysis - Analysed 8 years of exam papers with pandas to find which "
                "topics were most frequently examined, and rewrote the revision plan around it."),
            ]),
            ("EXPERIENCE", [
                "Mathematics Teacher, Vidya Public School, Bengaluru (2014 - Present)",
                "- Taught mathematics and statistics to 180 students per year across grades 9 to 12.",
                "- Designed and ran the school's first data driven attendance monitoring process.",
                "- Led a team of 4 teachers through a curriculum redesign for the statistics module.",
                "- Improved grade 12 mathematics pass rates from 78% to 91% over four years.",
                "- Trained 15 colleagues on using spreadsheets for assessment tracking.",
                "Private Mathematics Tutor, Self employed, Bengaluru (2013 - 2014)",
                "- Prepared 20 students for competitive entrance examinations.",
            ]),
            ("CERTIFICATIONS", [
                "Google Data Analytics Professional Certificate (2024)",
                "IBM Data Analyst Professional Certificate (2024)",
                "DataCamp Associate Data Analyst track (2023)",
            ]),
            ("EDUCATION", [
                "B.Ed Mathematics, Bangalore University (2013)",
                "BSc Mathematics, Christ University, Bengaluru (2011)",
            ]),
        ],
        "career_changer_in.pdf",
    )


def lead_in_remote() -> None:
    _render(
        "Kavya Iyer",
        "Pune, India  |  kavya.iyer@example.com  |  +91 89560 77321  |  Open to remote only",
        [
            ("PROFILE", [
                ("Lead data engineer with 11 years of experience designing high throughput ingestion "
                "platforms and mentoring engineering teams across distributed organisations. Has owned "
                "petabyte scale data infrastructure end to end, including cost, reliability and on call. "
                "Works remotely by preference and has led fully distributed teams across multiple time zones."),
            ]),
            ("TECH STACK", [
                ("Python, Scala, Spark, Kafka, Snowflake, dbt, Airflow, AWS, Terraform, Kubernetes, "
                "Flink, Databricks, Great Expectations, PostgreSQL"),
            ]),
            ("EXPERIENCE", [
                "Lead Data Engineer, Kestrel Systems, Pune (2020 - Present)",
                ("- Rebuilt the company's batch ingestion platform on Spark and Kafka, raising daily "
                "throughput from 12 million to 90 million events while reducing infrastructure spend "
                "by 35 percent across three AWS regions."),
                ("- Migrated 240 legacy SQL transformations into dbt, cutting the nightly warehouse "
                "build from 7 hours to 95 minutes and giving analysts self service model documentation "
                "for the first time."),
                ("- Introduced Great Expectations data quality checks across 60 critical tables, "
                "reducing data incidents reported by downstream teams from roughly 9 per month to 2."),
                ("- Led a team of 6 engineers distributed across Pune, Bengaluru and Singapore, running "
                "hiring, performance reviews and the on call rotation."),
                ("- Designed the streaming architecture that replaced a nightly batch with sub minute "
                "freshness for the fraud detection team, working with Flink and Kafka Streams."),
                ("- Reduced Snowflake spend by 28 percent through warehouse right sizing and clustering "
                "key changes, without any regression in query latency."),
                "Senior Data Engineer, Vertex Data Systems, Chennai (2016 - 2020)",
                ("- Owned the Airflow deployment running 380 daily DAGs for the finance and logistics "
                "domains, including on call rotation and post incident review."),
                ("- Built a change data capture pipeline from 14 PostgreSQL databases into the warehouse, "
                "replacing nightly full table dumps that had grown to 6 hours."),
                "- Mentored 4 junior engineers, two of whom were promoted to senior within two years.",
                "- Established the code review and testing standards still used by the data team.",
                "Data Engineer, Sundar Logistics, Ahmedabad (2014 - 2016)",
                "- Built the first ETL pipelines feeding the company's reporting warehouse.",
                "- Automated shipment reconciliation across 3 carrier APIs.",
            ]),
            ("LEADERSHIP AND COMMUNITY", [
                "Organiser, Pune Data Engineering meetup (2019 - Present)",
                "Speaker, Data Council India: Streaming Without the Tears (2023)",
                "Mentor, Women in Data India mentorship programme (2021 - Present)",
            ]),
            ("EDUCATION", [
                "B.Tech Computer Science, IIT Bombay (2012)",
            ]),
        ],
        "lead_in_remote.pdf",
    )


def mid_analyst_in() -> None:
    _render(
        "Ryan Patel",
        "Gurugram, India  |  ryan.patel@example.com  |  +91 99870 33456",
        [
            ("EDUCATION", [
                "BA Economics, Delhi University (2021)",
                "Minor in Statistics. Ranked in the top 5% of the Economics cohort, 2019 and 2020.",
            ]),
            ("SKILLS", [
                "SQL",
                "Excel",
                "Looker",
                "Python",
                "dbt",
                "Snowflake",
                "Tableau",
                "Google Analytics",
                "Data modelling",
                "Stakeholder reporting",
            ]),
            ("EXPERIENCE", [
                "Data Analyst, Cedarpoint Retail, Gurugram (2022 - Present)",
                "- Maintained 30 Looker dashboards for the merchandising and supply chain teams.",
                "- Automated a weekly sales report that previously took 6 hours to assemble by hand.",
                ("- Built the SQL models behind the company's store level margin reporting, now the "
                "source of truth for monthly business reviews."),
                ("- Partnered with the pricing team on a markdown analysis that recovered an estimated "
                "1.4M rupees of margin in one season."),
                "- Wrote the onboarding documentation for the analytics stack, used by 6 new joiners.",
                "- Ran a monthly office hours session teaching SQL basics to non technical staff.",
                "Business Analyst, Cedarpoint Retail, Gurugram (2021 - 2022)",
                "- Analysed store level sales performance across 45 retail locations.",
                "- Built the weekly trading pack circulated to regional managers.",
                ("- Investigated a stock discrepancy that traced back to a duplicated feed, preventing "
                "roughly 2,00,000 rupees of incorrect reorders."),
                "- Supported the annual budgeting cycle with historical trend analysis.",
                "Analytics Intern, Apex General Insurance, Noida (2020 - 2021)",
                "- Built claims summary reports in Excel and Tableau.",
                "- Cleaned and reconciled 5 years of policy data ahead of a system migration.",
            ]),
            ("ACHIEVEMENTS", [
                "Cedarpoint Retail Analyst of the Year (2023)",
                "Reduced reporting turnaround for the merchandising team from 3 days to same day.",
            ]),
        ],
        "mid_analyst_in.pdf",
    )


def main() -> None:
    junior_ds_in()
    senior_mle_in()
    career_changer_in()
    lead_in_remote()
    mid_analyst_in()


if __name__ == "__main__":
    main()
