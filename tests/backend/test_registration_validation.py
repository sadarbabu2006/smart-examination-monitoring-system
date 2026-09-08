"""Comprehensive tests for strict email & password validation, and invalid registration cleanup."""

import sqlite3
import pytest
from backend.app import create_app
from backend.app.services.auth_service import (
    ValidationError,
    DuplicateCandidateError,
    validate_email_address,
    validate_password_requirements,
    register_candidate,
)
from scripts.cleanup_invalid_registrations import cleanup_target_candidate


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


VALID_EMAILS = [
    "user@gmail.com",
    "student@gmail.com",
    "user.name@gmail.com",
    "user@yahoo.com",
    "user@yahoo.co.in",
    "user@outlook.com",
    "user@hotmail.com",
    "user@live.com",
    "user@icloud.com",
    "user@proton.me",
    "user@protonmail.com",
]

INVALID_EMAILS = [
    "dev@123.com",
    "abc@xyz.com",
    "test@random.com",
    "user@123.com",
    "candidate@fake.com",
    "debasmithrout@",
    "debasmithrout",
    "debasmithrout@gmail",
    "@gmail.com",
    "user@gmail",
    "user@.",
    "user@gmail.",
    "user@@gmail.com",
    "user name@gmail.com",
    "user..name@gmail.com",
    ".user@gmail.com",
    "user.@gmail.com",
    "debasmithrout@.",
    "debasmithrout@gmail.",
    "debasmithrout@@gmail.com",
    "debas@mith@gmail.com",
    "debas smith@gmail.com",
    "debas..mith@gmail.com",
]

VALID_PASSWORDS = [
    "Asecure1!",
    "Password1!",
    "ExamGuard9#",
]

INVALID_PASSWORDS = [
    "short1!",
    "password1!",
    "PASSWORD!",
    "Password!",
    "Password123",
    "Password123!",
]


def test_validate_email_address_valid():
    for email in VALID_EMAILS:
        normalized = validate_email_address(email)
        assert normalized == email.strip().lower(), f"Expected normalized email for {email}"


def test_validate_email_address_invalid():
    for email in INVALID_EMAILS:
        with pytest.raises(ValidationError, match="Please enter a valid email address."):
            validate_email_address(email)


def test_validate_password_requirements_valid():
    for pwd in VALID_PASSWORDS:
        validate_password_requirements(pwd)  # Should not raise


def test_validate_password_requirements_invalid():
    for pwd in INVALID_PASSWORDS:
        with pytest.raises(ValidationError):
            validate_password_requirements(pwd)


def test_api_registration_email_validation(client):
    valid_pwd = "ExamGuard9#"
    for invalid_email in INVALID_EMAILS:
        res = client.post(
            "/api/auth/register",
            json={
                "full_name": "Test Candidate",
                "email": invalid_email,
                "password": valid_pwd,
            },
        )
        assert res.status_code == 400, f"Expected 400 for email {invalid_email}, got {res.status_code}"
        data = res.get_json()
        assert "error" in data
        assert data["error"] == "Please enter a valid email address."


def test_regression_dev_at_123_com_rejected(client):
    """Specific regression test: dev@123.com MUST remain rejected with HTTP 400."""
    res = client.post(
        "/api/auth/register",
        json={
            "full_name": "Debasmith Rout",
            "email": "dev@123.com",
            "password": "ExamGuard9#",
        },
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "Please enter a valid email address."


def test_api_registration_password_validation(client):
    test_email_base = "pwd_test_{}@gmail.com"
    for idx, invalid_pwd in enumerate(INVALID_PASSWORDS):
        res = client.post(
            "/api/auth/register",
            json={
                "full_name": "Test Candidate",
                "email": test_email_base.format(idx),
                "password": invalid_pwd,
            },
        )
        assert res.status_code == 400, f"Expected 400 for password {invalid_pwd}, got {res.status_code}"
        data = res.get_json()
        assert "error" in data


def test_email_normalization_and_duplicate_prevention(client):
    res1 = client.post(
        "/api/auth/register",
        json={
            "full_name": "Case User One",
            "email": "  Candidate@gmail.com  ",
            "password": "ExamGuard9#",
        },
    )
    assert res1.status_code == 201
    candidate = res1.get_json()["candidate"]
    assert candidate["email"] == "candidate@gmail.com"
    assert "password" not in candidate
    assert "password_hash" not in candidate

    # Attempt registration with lowercase identical email
    res2 = client.post(
        "/api/auth/register",
        json={
            "full_name": "Case User Two",
            "email": "candidate@gmail.com",
            "password": "ExamGuard9#",
        },
    )
    assert res2.status_code == 409
    assert "already exists" in res2.get_json()["error"]


def test_api_registration_specific_cases(client):
    # Test debasmithrout@ -> HTTP 400
    res_fail = client.post(
        "/api/auth/register",
        json={
            "full_name": "Debasmith Rout",
            "email": "debasmithrout@",
            "password": "ExamGuard9#",
        },
    )
    assert res_fail.status_code == 400
    assert res_fail.get_json()["error"] == "Please enter a valid email address."

    # Test test@gmail.com with ExamGuard9# -> HTTP 201
    res_ok = client.post(
        "/api/auth/register",
        json={
            "full_name": "Test Candidate",
            "email": "test@gmail.com",
            "password": "ExamGuard9#",
        },
    )
    assert res_ok.status_code == 201
    cand = res_ok.get_json()["candidate"]
    assert cand["email"] == "test@gmail.com"
    assert "password" not in cand
    assert "password_hash" not in cand


def test_database_cleanup_target_candidate(tmp_path):
    """Test targeted candidate cleanup with backup creation and safety checks."""
    test_db = tmp_path / "test_cleanup.db"
    con = sqlite3.connect(test_db)
    con.row_factory = sqlite3.Row

    # Initialize schema
    from backend.app.database.db import init_db
    schema_sql = (tmp_path.parent.parent / "backend" / "app" / "database" / "schema.sql")
    # Read from project root
    import backend.app.database.db as db_mod
    from pathlib import Path
    schema_file = Path(db_mod.__file__).with_name("schema.sql")
    con.executescript(schema_file.read_text(encoding="utf-8"))

    # Seed valid candidate
    cur = con.execute(
        "INSERT INTO candidates (full_name, email, password_hash) VALUES (?, ?, ?)",
        ("Valid User", "valid_user@gmail.com", "hash_valid"),
    )
    valid_id = cur.lastrowid

    # Seed valid session
    cur = con.execute(
        "INSERT INTO exam_sessions (candidate_id, exam_identifier, status) VALUES (?, ?, 'active')",
        (valid_id, "EXAM-VALID"),
    )
    valid_session_id = cur.lastrowid

    # Seed target invalid candidate: dev@123.com
    dummy_photo = tmp_path / "dev_photo.jpg"
    dummy_photo.write_bytes(b"dummy photo bytes")
    cur = con.execute(
        "INSERT INTO candidates (full_name, email, username, password_hash, registration_photo_path) VALUES (?, ?, ?, ?, ?)",
        ("Debasmith Rout", "dev@123.com", "dev", "hash_dev", str(dummy_photo)),
    )
    target_id = cur.lastrowid

    # Seed candidate-owned session and records
    cur = con.execute(
        "INSERT INTO exam_sessions (candidate_id, exam_identifier, status) VALUES (?, ?, 'active')",
        (target_id, "EXAM-DEV"),
    )
    target_session_id = cur.lastrowid

    con.execute(
        "INSERT INTO monitoring_events (session_id, event_type, details) VALUES (?, 'SUSPICIOUS_FACE', 'details')",
        (target_session_id,),
    )
    con.execute(
        "INSERT INTO face_absence_intervals (session_id, started_at, ended_at, duration_seconds) VALUES (?, '2026-09-01 10:00:00', '2026-09-01 10:00:05', 5.0)",
        (target_session_id,),
    )
    con.execute(
        "INSERT INTO integrity_scores (session_id, integrity_score, risk_level, breakdown) VALUES (?, 85, 'LOW', '{}')",
        (target_session_id,),
    )

    # Seed admin/proctor
    con.execute(
        "INSERT INTO proctor_admins (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("Lead Admin", "admin@examguard.test", "hash_admin", "ADMIN"),
    )
    con.commit()
    con.close()

    # Execute cleanup
    result = cleanup_target_candidate(db_path=test_db, target_email="dev@123.com")
    assert result["status"] == "deleted"
    assert result["candidate_id"] == target_id
    assert Path(result["backup_path"]).exists()
    assert not dummy_photo.exists()

    # Verify database contents
    con = sqlite3.connect(test_db)
    assert con.execute("SELECT 1 FROM candidates WHERE email = 'dev@123.com'").fetchone() is None
    assert con.execute("SELECT 1 FROM exam_sessions WHERE id = ?", (target_session_id,)).fetchone() is None
    assert con.execute("SELECT 1 FROM monitoring_events WHERE session_id = ?", (target_session_id,)).fetchone() is None
    assert con.execute("SELECT 1 FROM face_absence_intervals WHERE session_id = ?", (target_session_id,)).fetchone() is None
    assert con.execute("SELECT 1 FROM integrity_scores WHERE session_id = ?", (target_session_id,)).fetchone() is None

    # Verify valid records remain intact
    assert con.execute("SELECT 1 FROM candidates WHERE id = ?", (valid_id,)).fetchone() is not None
    assert con.execute("SELECT 1 FROM exam_sessions WHERE id = ?", (valid_session_id,)).fetchone() is not None
    assert con.execute("SELECT 1 FROM proctor_admins WHERE email = 'admin@examguard.test'").fetchone() is not None
    con.close()

    # Test idempotency on second run
    result2 = cleanup_target_candidate(db_path=test_db, target_email="dev@123.com")
    assert result2["status"] == "not_found"


def test_create_app_does_not_automatically_cleanup(monkeypatch, tmp_path):
    cleanup_called = False

    def fake_cleanup(db_path=None, target_email="dev@123.com"):
        nonlocal cleanup_called
        cleanup_called = True
        return {"status": "mock"}

    import scripts.cleanup_invalid_registrations as script_mod
    monkeypatch.setattr(script_mod, "cleanup_target_candidate", fake_cleanup)

    _ = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE_PATH": str(tmp_path / "examguard.db"),
        "REGISTRATION_PHOTO_DIR": str(tmp_path / "photos"),
    })

    assert cleanup_called is False, "create_app() must NOT automatically call cleanup"


def test_api_registration_with_captured_webcam_photo(client):
    """Test candidate registration flow using canvas toDataURL JPEG base64 payload."""
    import base64
    from pathlib import Path
    import cv2
    import numpy as np

    # Generate a dummy 64x64 valid JPEG frame simulating canvas.toDataURL("image/jpeg")
    frame = np.full((64, 64, 3), 120, dtype=np.uint8)
    success, buffer = cv2.imencode(".jpg", frame)
    assert success
    b64_data = base64.b64encode(buffer.tobytes()).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{b64_data}"

    res = client.post(
        "/api/auth/register",
        json={
            "full_name": "Webcam Candidate",
            "email": "webcam_candidate@gmail.com",
            "password": "ExamGuard9#",
            "photo_base64": data_url,
        },
    )
    assert res.status_code == 201
    data = res.get_json()
    cand = data["candidate"]
    assert cand["email"] == "webcam_candidate@gmail.com"
    assert cand["registration_photo_path"] is not None

    photo_path = Path(cand["registration_photo_path"])
    assert photo_path.exists()
    assert photo_path.suffix == ".jpg"
    assert photo_path.stat().st_size > 0

    # Verify candidate login succeeds
    login_res = client.post(
        "/api/auth/login",
        json={
            "email": "webcam_candidate@gmail.com",
            "password": "ExamGuard9#",
        },
    )
    assert login_res.status_code == 200
    assert login_res.get_json()["authenticated"] is True

