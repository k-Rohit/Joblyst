import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, UploadFile

from joblyst.exceptions import CVReadError
from joblyst.profile import extract_profile
from joblyst.tools.cv_reader import extract_cv_content

app = FastAPI()

SESSIONS: dict[UUID, dict] = {}


@app.get("/")
@app.get("/health")
def check_status():
    return {"status": "healthy"}


@app.post("/api/profile")
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
    profile = extract_profile(cv_content, thread_id=str(thread_id), tags=["api", "extract"])
    SESSIONS[thread_id] = {"cv_text": cv_content, "profile": profile}
    return {"thread_id": thread_id, "profile": profile}
