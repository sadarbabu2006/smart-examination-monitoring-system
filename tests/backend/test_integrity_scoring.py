"""Unit and integration tests for ExamGuard Integrity Scoring Engine."""

import pytest
from datetime import datetime, timedelta, timezone

from backend.app.services.integrity_scoring import (
    IntegrityScoringConfig,
    calculate_face_presence_ratio,
    calculate_session_duration,
    calculate_session_integrity,
    evaluate_and_persist_session_integrity,
    get_integrity_score,
    save_integrity_score,
)
from backend.app import create_app
from backend.app.services.event_logger import log_event, record_face_absence_interval


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


def _register_and_login(client, email="candidate@examguard.test", password="Safe-password-123!"):
    client.post("/api/auth/register", json={
        "full_name": "Test Candidate",
        "email": email,
        "password": password
    })
    client.post("/api/auth/login", json={"email": email, "password": password})


def _create_and_start_session(client, exam_id="CS-101"):
    res = client.post("/api/exam-sessions", json={"exam_identifier": exam_id})
    session_id = res.get_json()["session"]["id"]
    client.post(f"/api/exam-sessions/{session_id}/start")
    return session_id


def test_integrity_scoring_test1_perfect_session(client, app):
    """TEST 1: Perfect session - no violations, full presence -> score 100, LOW risk."""
    _register_and_login(client, "perfect@test.com")
    session_id = _create_and_start_session(client, "EXAM-PERFECT")

    with app.app_context():
        res = calculate_session_integrity(session_id)
        assert res["integrity_score"] == 100
        assert res["risk_level"] == "LOW"
        assert res["suspicious_event_count"] == 0
        assert res["breakdown"]["total_deductions"] == 0
        assert res["breakdown"]["base_score"] == 100


def test_integrity_scoring_test2_small_violations(client, app):
    """TEST 2: Small number of violations -> moderate deduction, LOW risk."""
    _register_and_login(client, "minor@test.com")
    session_id = _create_and_start_session(client, "EXAM-MINOR")

    with app.app_context():
        # 1 tab switch (5 pts) and 1 focus loss (3 pts) -> total 8 pts deduction
        log_event(session_id, "tab_switch")
        log_event(session_id, "focus_loss")

        res = calculate_session_integrity(session_id)
        assert res["integrity_score"] == 92
        assert res["risk_level"] == "LOW"
        assert res["breakdown"]["deductions"]["tab_switch"] == 5
        assert res["breakdown"]["deductions"]["focus_loss"] == 3
        assert res["breakdown"]["total_deductions"] == 8


def test_integrity_scoring_test3_repeated_violations(client, app):
    """TEST 3: Repeated tab/focus violations -> significant deduction, MEDIUM risk."""
    _register_and_login(client, "repeated@test.com")
    session_id = _create_and_start_session(client, "EXAM-REPEATED")

    with app.app_context():
        # 6 tab switches (30 pts) + 4 focus losses (12 pts) -> 42 pts deduction -> score 58 (MEDIUM)
        for _ in range(6):
            log_event(session_id, "tab_switch")
        for _ in range(4):
            log_event(session_id, "focus_loss")

        res = calculate_session_integrity(session_id)
        assert res["integrity_score"] == 58
        assert res["risk_level"] == "MEDIUM"
        assert res["breakdown"]["deductions"]["tab_switch"] == 30
        assert res["breakdown"]["deductions"]["focus_loss"] == 12
        assert res["breakdown"]["total_deductions"] == 42


def test_integrity_scoring_test4_multiple_faces(client, app):
    """TEST 4: Multiple-face events -> 15 pts deduction per occurrence."""
    _register_and_login(client, "multi@test.com")
    session_id = _create_and_start_session(client, "EXAM-MULTI")

    with app.app_context():
        # 2 multiple face events -> 30 pts deduction -> score 70 (MEDIUM)
        log_event(session_id, "multiple_faces")
        log_event(session_id, "multiple_faces")

        res = calculate_session_integrity(session_id)
        assert res["breakdown"]["deductions"]["multiple_faces"] == 30
        assert res["integrity_score"] == 70
        assert res["risk_level"] == "MEDIUM"


def test_integrity_scoring_test5_face_presence_ratio_and_prolonged_absence(client, app):
    """TEST 5: Prolonged face absence -> duration-based deduction and accurate presence ratio."""
    _register_and_login(client, "absence@test.com")
    session_id = _create_and_start_session(client, "EXAM-ABSENCE")

    with app.app_context():
        # Record 60 seconds of face absence (5 pts per 30s = 10 pts deduction)
        now = datetime.now(timezone.utc)
        record_face_absence_interval(
            session_id=session_id,
            started_at=(now - timedelta(seconds=60)).isoformat(),
            ended_at=now.isoformat(),
            duration_seconds=60.0
        )

        res = calculate_session_integrity(session_id)
        assert res["face_absence_seconds"] == 60.0
        assert res["breakdown"]["deductions"]["face_absence"] == 10
        assert res["integrity_score"] == 90
        assert res["risk_level"] == "LOW"


def test_integrity_scoring_test6_extreme_violations_capped_at_zero(client, app):
    """TEST 6: Extreme violations -> score clamped at 0, risk HIGH (never < 0)."""
    _register_and_login(client, "extreme@test.com")
    session_id = _create_and_start_session(client, "EXAM-EXTREME")

    with app.app_context():
        # 15 tab switches (75 pts) + 10 focus losses (30 pts) + 3 multiple faces (45 pts) -> 150 pts deduction
        for _ in range(15):
            log_event(session_id, "tab_switch")
        for _ in range(10):
            log_event(session_id, "focus_loss")
        for _ in range(3):
            log_event(session_id, "multiple_faces")

        res = calculate_session_integrity(session_id)
        assert res["breakdown"]["total_deductions"] == 150
        assert res["integrity_score"] == 0  # Clamped at 0
        assert res["risk_level"] == "HIGH"


def test_integrity_scoring_test7_no_duration_edge_case():
    """TEST 7: No monitoring duration -> safe handling without division-by-zero crash."""
    ratio = calculate_face_presence_ratio(total_absence_seconds=0.0, monitored_duration_seconds=0.0)
    assert ratio is None

    ratio_negative = calculate_face_presence_ratio(total_absence_seconds=10.0, monitored_duration_seconds=-5.0)
    assert ratio_negative is None

    # Normal case
    ratio_normal = calculate_face_presence_ratio(total_absence_seconds=30.0, monitored_duration_seconds=120.0)
    assert ratio_normal == 0.75


def test_integrity_scoring_test8_missing_telemetry(client, app):
    """TEST 8: Missing/incomplete telemetry -> safe default handling without crash."""
    _register_and_login(client, "missing@test.com")
    session_id = _create_and_start_session(client, "EXAM-EMPTY")

    with app.app_context():
        res = calculate_session_integrity(session_id)
        assert res["integrity_score"] == 100
        assert res["risk_level"] == "LOW"
        assert res["face_absence_seconds"] == 0.0


def test_integrity_scoring_test9_idempotent_scoring(client, app):
    """TEST 9: Repeated scoring -> updates existing record without duplicate rows or errors."""
    _register_and_login(client, "idempotent@test.com")
    session_id = _create_and_start_session(client, "EXAM-IDEMPOTENT")

    with app.app_context():
        res1 = evaluate_and_persist_session_integrity(session_id)
        assert res1 is not None
        assert res1["session_id"] == session_id

        # Score again after logging an event
        log_event(session_id, "tab_switch")
        res2 = evaluate_and_persist_session_integrity(session_id)
        assert res2 is not None
        assert res2["integrity_score"] == 95

        # Check DB row count for this session
        score_record = get_integrity_score(session_id)
        assert score_record["integrity_score"] == 95


def test_integrity_scoring_test10_exam_submission_flow_and_api(client, app):
    """TEST 10 & 11: Examination submission calculates score and API returns structured JSON."""
    _register_and_login(client, "submitter@test.com")
    session_id = _create_and_start_session(client, "EXAM-SUBMIT")

    # Log violations while active
    client.post("/api/monitoring/events", json={
        "session_id": session_id,
        "event_type": "tab_switch"
    })
    client.post("/api/monitoring/events", json={
        "session_id": session_id,
        "event_type": "focus_loss"
    })

    # Submit the examination session
    submit_res = client.post(f"/api/exam-sessions/{session_id}/submit")
    assert submit_res.status_code == 200
    session_data = submit_res.get_json()["session"]
    assert session_data["status"] == "submitted"
    assert "integrity_score" not in session_data
    assert "risk_level" not in session_data

    # Verify score was properly computed and persisted in the database
    with app.app_context():
        persisted = get_integrity_score(session_id)
        assert persisted is not None
        assert persisted["integrity_score"] == 92
        assert persisted["risk_level"] == "LOW"

    # Query administrative/proctoring GET /api/exam-sessions/<id>/integrity
    integrity_res = client.get(f"/api/exam-sessions/{session_id}/integrity")
    assert integrity_res.status_code == 200
    data = integrity_res.get_json()
    assert data["session_id"] == session_id
    assert data["integrity_score"] == 92
    assert data["risk_level"] == "LOW"
    assert data["event_summary"]["tab_switch"] == 1
    assert data["event_summary"]["focus_loss"] == 1
    assert "breakdown" in data
    assert data["breakdown"]["base_score"] == 100
    assert data["breakdown"]["total_deductions"] == 8


def test_integrity_scoring_auth_and_ownership(client):
    """Verify integrity route requires authentication and ownership validation."""
    # 1. Unauthenticated request -> 401
    res = client.get("/api/exam-sessions/1/integrity")
    assert res.status_code == 401

    # 2. Register Candidate A and create session
    _register_and_login(client, "cand_a@test.com")
    session_id = _create_and_start_session(client, "EXAM-A")
    client.post(f"/api/exam-sessions/{session_id}/submit")

    # 3. Register Candidate B and try to access Candidate A's session -> 403
    _register_and_login(client, "cand_b@test.com")
    forbidden_res = client.get(f"/api/exam-sessions/{session_id}/integrity")
    assert forbidden_res.status_code == 403


def test_candidate_results_page_does_not_render_integrity_telemetry(client):
    """Verify candidate dashboard Results page contains academic placeholders and NO integrity metrics."""
    _register_and_login(client, "academic@test.com")
    res = client.get("/dashboard")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # 1. Academic result structure exists
    assert "Examination Results" in html
    assert "Marks Obtained" in html
    assert "Percentage" in html
    assert "Grade" in html
    assert "Evaluation Status" in html
    assert "Result Pending" in html

    # 2. Integrity/proctoring metrics are NOT exposed in candidate dashboard
    assert "/integrity" not in html
    assert "toggleBreakdown" not in html
    assert "Deterministic Deduction Breakdown" not in html


def test_candidate_session_api_payload_does_not_leak_integrity_data(client, app):
    """Verify candidate session endpoints return academic session info without leaking integrity metrics."""
    _register_and_login(client, "noleak@test.com")
    session_id = _create_and_start_session(client, "EXAM-NOLEAK")

    # Add violation event and submit
    client.post("/api/monitoring/events", json={"session_id": session_id, "event_type": "tab_switch"})
    submit_res = client.post(f"/api/exam-sessions/{session_id}/submit")
    assert submit_res.status_code == 200
    submitted_sess = submit_res.get_json()["session"]
    assert submitted_sess["status"] == "submitted"
    assert "integrity_score" not in submitted_sess
    assert "risk_level" not in submitted_sess
    assert "face_presence_ratio" not in submitted_sess

    # Query GET /api/exam-sessions (candidate session list)
    list_res = client.get("/api/exam-sessions")
    assert list_res.status_code == 200
    sessions = list_res.get_json()["sessions"]
    target = next(s for s in sessions if s["id"] == session_id)
    assert "integrity_score" not in target
    assert "risk_level" not in target
    assert "face_presence_ratio" not in target

    # Query GET /api/exam-sessions/<id> (single session)
    detail_res = client.get(f"/api/exam-sessions/{session_id}")
    assert detail_res.status_code == 200
    detail = detail_res.get_json()["session"]
    assert "integrity_score" not in detail
    assert "risk_level" not in detail
    assert "face_presence_ratio" not in detail

    # Meanwhile, proctor/admin backend integrity data IS properly computed and persisted in DB
    with app.app_context():
        persisted = get_integrity_score(session_id)
        assert persisted is not None
        assert persisted["integrity_score"] == 95
        assert persisted["risk_level"] == "LOW"

