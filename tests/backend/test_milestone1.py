import sqlite3

import numpy as np
import pytest

from backend.app import create_app
from backend.app.database.db import get_db
from computer_vision.registration_photo import save_registration_frame


@pytest.fixture()
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE_PATH": str(tmp_path / "examguard.db"),
        "REGISTRATION_PHOTO_DIR": str(tmp_path / "photos"),
    })


@pytest.fixture()
def client(app):
    return app.test_client()


def register(client, email="ada@example.test", password="Safe-password-123!"):
    return client.post("/api/auth/register", json={"full_name": "Ada Candidate", "email": email, "password": password})


def test_database_schema_and_foreign_key(app):
    with app.app_context():
        db = get_db()
        tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"candidates", "exam_sessions"}.issubset(tables)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO exam_sessions (candidate_id, exam_identifier) VALUES (?, ?)", (999, "EXAM-1"))


def test_registration_duplicates_and_password_protection(app, client):
    # Test invalid passwords
    assert client.post("/api/auth/register", json={"full_name": "P1", "email": "p1@example.test", "password": "Short1!"}).status_code == 400
    assert client.post("/api/auth/register", json={"full_name": "P2", "email": "p2@example.test", "password": "lowercaseonly123!"}).status_code == 400
    assert client.post("/api/auth/register", json={"full_name": "P3", "email": "p3@example.test", "password": "NoNumberHere!"}).status_code == 400
    assert client.post("/api/auth/register", json={"full_name": "P4", "email": "p4@example.test", "password": "NoSpecialChar123"}).status_code == 400

    # Test valid password WITHOUT lowercase (lowercase not required)
    res_nolower = client.post("/api/auth/register", json={"full_name": "No Lower", "email": "nolower@example.test", "password": "ALLUPPERCASE123!"})
    assert res_nolower.status_code == 201

    response = register(client)
    assert response.status_code == 201
    candidate = response.get_json()["candidate"]
    assert "password" not in candidate and "password_hash" not in candidate
    assert register(client).status_code == 409
    with app.app_context():
        row = get_db().execute("SELECT password_hash FROM candidates WHERE email = ?", ("ada@example.test",)).fetchone()
        assert row["password_hash"] != "Safe-password-123!"
        assert row["password_hash"].startswith("scrypt:") or row["password_hash"].startswith("pbkdf2:")


def test_health_and_saved_registration_photo_path(app, client):
    assert client.get("/api/health").get_json()["status"] == "ok"
    with app.app_context():
        photo_path = save_registration_frame(
            np.zeros((10, 10, 3), dtype=np.uint8), app.config["REGISTRATION_PHOTO_DIR"]
        )
    response = client.post("/api/auth/register", json={
        "full_name": "Photo Candidate", "email": "photo@example.test", "password": "Safe-password-123!",
        "registration_photo_path": photo_path,
    })
    assert response.status_code == 201
    assert response.get_json()["candidate"]["registration_photo_path"] == photo_path


def test_login_credentials(client):
    register(client)
    assert client.post("/api/auth/login", json={"email": "ada@example.test", "password": "Safe-password-123!"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "ada@example.test", "password": "incorrect"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "unknown@example.test", "password": "Safe-password-123!"}).status_code == 401


def test_session_lifecycle_and_candidate_ownership(client):
    register(client, "one@example.test")
    client.post("/api/auth/login", json={"email": "one@example.test", "password": "Safe-password-123!"})
    created = client.post("/api/exam-sessions", json={"exam_identifier": "M1-DEMO"})
    session_id = created.get_json()["session"]["id"]
    assert created.get_json()["session"]["status"] == "scheduled"
    assert client.post(f"/api/exam-sessions/{session_id}/pause").status_code == 409
    for action, state in (("start", "active"), ("pause", "paused"), ("resume", "active"), ("submit", "submitted")):
        response = client.post(f"/api/exam-sessions/{session_id}/{action}")
        assert response.status_code == 200
        assert response.get_json()["session"]["status"] == state
    assert client.post(f"/api/exam-sessions/{session_id}/start").status_code == 409

    other = client.application.test_client()
    register(other, "two@example.test")
    other.post("/api/auth/login", json={"email": "two@example.test", "password": "Safe-password-123!"})
    assert other.get(f"/api/exam-sessions/{session_id}").status_code == 403
