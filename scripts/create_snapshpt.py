import json
import time
from pathlib import Path

from joblyst.schemas.schemas import JobPosting
from joblyst.tools.search_job import (
    CACHE_PATH,
    AdzunaSource,
    HimalayasSource,
    RemotiveSource,
    _dedup_jobs,
)

# cap for each job board -
_REMOTIVE_QUOTA = 5
_ADZUNA_QUOTA = 5
_HIMALAYAS_QUOTA = 5

QUERIES = [
    "data scientist",
    "junior data scientist",
    "machine learning engineer",
    "senior machine learning engineer",
    "data analyst",
    "business analyst",
    "data engineer",
    "senior data engineer",
    "analytics engineer",
    "AI engineer",
    "Gen AI Engineer",
]


def _dump_postings(jobs: list[JobPosting], path: Path = CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([job.model_dump() for job in jobs], indent=2, ensure_ascii=False)
    )
    print(f"wrote {(len(jobs))} postings to {path}")


def collect_jobs() -> list[JobPosting]:

    jobs: list[JobPosting] = []

    # create the clients -
    adzuna = AdzunaSource()
    remotive = RemotiveSource()
    himalayas = HimalayasSource()

    if adzuna.available:
        print("Adzuna key found! - Retrieving postings...")
        for q in QUERIES:
            adzuna_jobs = adzuna.fetch(
                query=q, location="", country="in", remote=False, limit=_ADZUNA_QUOTA
            )
            jobs.extend(adzuna_jobs)
            time.sleep(0.3)
    else:
        print(
            "No Adzuna keys — skipping (cache will be Remotive and Himalayas only, all remote)."
        )

    print("Adding jobs fetched from remotive")
    for q in QUERIES:
        remotive_jobs = remotive.fetch(
            query=q, location="", country="in", remote=False, limit=_REMOTIVE_QUOTA
        )
        jobs.extend(remotive_jobs)

    print("Adding jobs fetched from himalayas.")
    for q in QUERIES:
        himalayas_jobs = himalayas.fetch(
            query=q, location="", country="in", remote=False, limit=_HIMALAYAS_QUOTA
        )
        jobs.extend(himalayas_jobs)

    deduped_jobs = _dedup_jobs(jobs=jobs)
    _dump_postings(deduped_jobs, CACHE_PATH)
    return deduped_jobs


if __name__ == "__main__":
    collect_jobs()
