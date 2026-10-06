from uuid import uuid4

from fastapi.testclient import TestClient

from joblyst.api import main

client = TestClient(main.app)

# test the /api/profile route -


def test_profile_rejects_a_non_pdf():
    r = client.post(
        "/api/profile",
        files={"file": ("resume.txt", b"plain text resume", "text/plain")},
    )
    assert r.status_code == 400
    assert "is not a PDF" in r.json()["detail"]


def test_broken_pdf():
    r = client.post(
        "/api/profile", files={"file": ("resume.pdf", b"broken pdf", "application/pdf")}
    )
    assert r.status_code == 400


# test the /api/search route -


def test_search_with_unknown_thread_is_404():
    tid = uuid4()
    r = client.post(
        "/api/search",
        json={"thread_id": str(tid), "locations": ["Bangalore"], "remote_ok": True},
    )
    assert r.status_code == 404
    assert "Unknown thread_id" in r.json()["detail"]


def test_search_with_malformed_thread_id_is_422():
    # FastAPI rejects it from SearchRequest's `thread_id: UUID` — the route never runs.
    r = client.post(
        "/api/search", json={"thread_id": "abc", "locations": ["Bangalore"]}
    )
    assert r.status_code == 422


def test_search_without_locations_is_422():
    r = client.post("/api/search", json={"thread_id": str(uuid4())})
    assert r.status_code == 422
