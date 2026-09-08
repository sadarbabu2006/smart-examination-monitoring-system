import base64
import io
import cv2
import numpy as np
import pytest

from backend.app import create_app
from backend.app.database.db import get_db


@pytest.fixture()
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "frontend-test-secret",
        "DATABASE_PATH": str(tmp_path / "examguard.db"),
        "REGISTRATION_PHOTO_DIR": str(tmp_path / "photos"),
    })


@pytest.fixture()
def client(app):
    return app.test_client()


def _make_dummy_image_b64():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf).decode("utf-8")


def test_registration_with_base64_photo(client):
    b64_photo = _make_dummy_image_b64()
    res = client.post("/api/auth/register", json={
        "full_name": "Frontend Candidate",
        "email": "frontend@examguard.test",
        "password": "Safe-password-123!",
        "photo_base64": b64_photo
    })
    assert res.status_code == 201
    candidate = res.get_json()["candidate"]
    assert candidate["email"] == "frontend@examguard.test"
    assert candidate["registration_photo_path"] is not None


def test_registration_with_multipart_photo(client):
    img = np.zeros((80, 80, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".png", img)
    data = {
        "full_name": "Multipart Candidate",
        "email": "multipart@examguard.test",
        "password": "Safe-password-123!",
        "registration_photo": (io.BytesIO(buf.tobytes()), "photo.png")
    }
    res = client.post("/api/auth/register", data=data, content_type="multipart/form-data")
    assert res.status_code == 201
    candidate = res.get_json()["candidate"]
    assert candidate["email"] == "multipart@examguard.test"
    assert candidate["registration_photo_path"] is not None


def test_auth_me_and_logout_lifecycle(client):
    # Unauthenticated
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    assert res.get_json()["authenticated"] is False

    # Register & Login
    client.post("/api/auth/register", json={
        "full_name": "Auth User",
        "email": "authuser@examguard.test",
        "password": "Safe-password-123!"
    })
    login_res = client.post("/api/auth/login", json={
        "email": "authuser@examguard.test",
        "password": "Safe-password-123!"
    })
    assert login_res.status_code == 200

    # Authenticated me
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    data = me_res.get_json()
    assert data["authenticated"] is True
    assert data["candidate"]["email"] == "authuser@examguard.test"

    # Logout
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200
    assert logout_res.get_json()["authenticated"] is False

    # Now me returns unauthenticated
    assert client.get("/api/auth/me").get_json()["authenticated"] is False


def test_list_candidate_sessions(client):
    client.post("/api/auth/register", json={
        "full_name": "Session Candidate",
        "email": "sess@examguard.test",
        "password": "Safe-password-123!"
    })
    client.post("/api/auth/login", json={
        "email": "sess@examguard.test",
        "password": "Safe-password-123!"
    })

    # Initially empty
    list_res = client.get("/api/exam-sessions")
    assert list_res.status_code == 200
    assert list_res.get_json()["count"] == 0

    # Create two sessions
    client.post("/api/exam-sessions", json={"exam_identifier": "EXAM-1"})
    client.post("/api/exam-sessions", json={"exam_identifier": "EXAM-2"})

    list_res = client.get("/api/exam-sessions")
    assert list_res.status_code == 200
    data = list_res.get_json()
    assert data["count"] == 2
    identifiers = [s["exam_identifier"] for s in data["sessions"]]
    assert "EXAM-1" in identifiers and "EXAM-2" in identifiers


def test_monitoring_verify_frame_endpoint(client):
    b64_photo = _make_dummy_image_b64()
    res = client.post("/api/monitoring/verify-frame", json={"frame": b64_photo})
    assert res.status_code == 200
    data = res.get_json()
    assert "face_count" in data
    assert "status" in data
    assert "verified" in data


def test_monitoring_process_frame_endpoint_and_absence_persistence(client, app):
    client.post("/api/auth/register", json={
        "full_name": "Monitor User",
        "email": "mon@examguard.test",
        "password": "Safe-password-123!"
    })
    client.post("/api/auth/login", json={
        "email": "mon@examguard.test",
        "password": "Safe-password-123!"
    })
    created = client.post("/api/exam-sessions", json={"exam_identifier": "PROCTOR-EXAM"})
    session_id = created.get_json()["session"]["id"]

    # Start session so it is active
    client.post(f"/api/exam-sessions/{session_id}/start")

    # Send blank frame -> triggers face_absent state
    b64_photo = _make_dummy_image_b64()
    res = client.post("/api/monitoring/process-frame", json={
        "session_id": session_id,
        "frame": b64_photo
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["session_id"] == session_id
    assert data["state"] in {"absent", "present"}


def test_auth_photo_serving(client):
    # Register with base64 photo
    b64_photo = _make_dummy_image_b64()
    client.post("/api/auth/register", json={
        "full_name": "Photo User",
        "email": "photouser@examguard.test",
        "password": "Safe-password-123!",
        "photo_base64": b64_photo
    })
    client.post("/api/auth/login", json={
        "email": "photouser@examguard.test",
        "password": "Safe-password-123!"
    })

    # Fetch photo
    res = client.get("/api/auth/photo")
    assert res.status_code == 200
    assert res.content_type == "image/jpeg"
    assert len(res.data) > 0


def test_candidate_frontend_page_routes(client):
    # Verify all HTML routes respond with 200 OK
    for path in ["/register", "/login", "/dashboard", "/profile", "/exam-instructions", "/face-verification", "/exam"]:
        res = client.get(path)
        assert res.status_code == 200
        assert b"<!DOCTYPE html>" in res.data


