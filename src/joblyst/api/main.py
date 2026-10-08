import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile, status

from joblyst.api import sessions
from joblyst.api.schemas import (
    ExternalJobRequest,
    ProfileResponse,
    SearchRequest,
    SearchResponse,
    TailorRequest,
    TailorResponse,
)
from joblyst.db import close_pool, open_pool
from joblyst.exceptions import CVReadError
from joblyst.profile import extract_profile
from joblyst.runner import run_external_job, run_search, run_tailor
from joblyst.tools.cv_reader import extract_cv_content


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    open_pool()
    yield

    # shutdown
    close_pool()


app = FastAPI(lifespan=lifespan)


@app.get("/")
@app.get("/health")
def check_status():
    return {"status": "healthy"}


@app.post(
    "/api/profile", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED
)
def upload_profile(file: UploadFile):
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail=f"{file.filename} is not a PDF (got {file.content_type}).",
        )

    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(file.file.read())
        tmp.flush()
        try:
            cv_content = extract_cv_content(Path(tmp.name))
        except CVReadError as exc:
            detail = str(exc).replace(Path(tmp.name).name, file.filename or "your CV")
            raise HTTPException(status_code=400, detail=detail) from exc

    thread_id = uuid4()
    # UUID is the API's own id format; the core (LangGraph, Opik, batch scripts) uses
    # plain string ids, so convert at this boundary only.
    profile = extract_profile(
        cv_content, thread_id=str(thread_id), tags=["api", "extract"]
    )
    sessions.save(thread_id, cv_content, profile)
    return ProfileResponse(thread_id=thread_id, profile=profile)


@app.post("/api/search", response_model=SearchResponse)
def search(req: SearchRequest):
    # check what is stored in the current session (mainly for profile as that will
    # help the llm to write the search query)
    session = sessions.get(req.thread_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown thread_id {req.thread_id}. Upload a CV first.",
        )

    # 2. apply this search's preferences — the CV can't answer these
    profile = session["profile"].model_copy(
        update={"locations": req.locations, "remote_ok": req.remote_ok}
    )

    result = run_search(
        profile,
        session["cv_text"],
        thread_id=str(req.thread_id),
        tags=["api", "search"],
        target_role=req.target_role,
    )

    return SearchResponse(
        thread_id=req.thread_id,
        jobs=result.ranked_jobs,
        sources=result.jobs_sources,
        reformulation_count=result.reformulation_count,
    )


@app.post("/api/tailor", response_model=TailorResponse)
def tailor(req: TailorRequest):
    session = sessions.get(req.thread_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown thread_id {req.thread_id}. Upload a CV first.",
        )

    result = run_tailor(
        thread_id=str(req.thread_id), selected_job_id=req.selected_job_id
    )

    # No pack means tailoring refused. run_tailor doesn't reset `errors`, so the
    # list still holds this thread's search messages; the tailor node's reason is
    # the last entry. Matching on its wording ties this to graph/nodes/tailor.py.
    if not result.pack:
        reason = result.errors[-1] if result.errors else "Tailoring failed."
        if "run a job search first" in reason:
            status_code = 409  # right thread, wrong order: no search has run yet
        elif "is not among" in reason:
            status_code = 404  # the job id isn't one of this thread's ranked jobs
        else:
            status_code = (
                500  # e.g. empty corpus — can't happen via this API, so a server bug
            )
        raise HTTPException(status_code=status_code, detail=reason)

    return TailorResponse(
        thread_id=req.thread_id,
        pack=result.pack,
        fabrication_report=result.fabrication_report,  # type: ignore
    )


@app.post("/api/external-job", response_model=TailorResponse)
def external(req: ExternalJobRequest):
    session = sessions.get(req.thread_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown thread_id {req.thread_id}. Upload a CV first.",
        )
    result = run_external_job(
        session["profile"],
        session["cv_text"],
        thread_id=str(req.thread_id),
        external_job_text=req.job_desc,
    )

    if not result.pack:
        reason = result.errors[-1] if result.errors else "Tailoring failed."
        if "is not among" in reason:
            reason = "Could not score the pasted job, so it could not be tailored. Please try again."
        raise HTTPException(status_code=502, detail=reason)

    return TailorResponse(
        thread_id=req.thread_id,
        pack=result.pack,
        fabrication_report=result.fabrication_report,  # type: ignore
    )
