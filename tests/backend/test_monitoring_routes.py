import pytest

from backend.app import create_app


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


def setup_candidate_and_session(client, email="ada@example.test", start=True):
    client.post("/api/auth/register", json={"full_name": "Ada Candidate", "email": email, "password": "safe-password"})
    client.post("/api/auth/login", json={"email": email, "password": "safe-password"})
    res = client.post("/api/exam-sessions", json={"exam_identifier": "EXAM-101"})
    session_id = res.get_json()["session"]["id"]
    if start:
        client.post(f"/api/exam-sessions/{session_id}/start")
    return session_id


def test_auth_required_for_monitoring_routes(client):
    assert client.post("/api/monitoring/events", json={"session_id": 1, "event_type": "tab_switch"}).status_code == 401
    assert client.get("/api/monitoring/events/1").status_code == 401
    assert client.post("/api/monitoring/face-absence", json={"session_id": 1, "started_at": "2026-08-30T10:00:00Z"}).status_code == 401
    assert client.get("/api/monitoring/face-absence/1").status_code == 401
    assert client.get("/api/monitoring/suspicious-events/1").status_code == 401


def test_ownership_and_state_verification(client):
    session_id = setup_candidate_and_session(client, "candidate1@example.test", start=False)

    # Session is scheduled (not active), should return 409
    res = client.post("/api/monitoring/events", json={"session_id": session_id, "event_type": "tab_switch"})
    assert res.status_code == 409

    # Start the session
    client.post(f"/api/exam-sessions/{session_id}/start")

    # Now post succeeds
    res = client.post("/api/monitoring/events", json={"session_id": session_id, "event_type": "tab_switch"})
    assert res.status_code == 201

    # Switch candidate
    other_client = client.application.test_client()
    setup_candidate_and_session(other_client, "candidate2@example.test", start=True)

    # Candidate 2 cannot access Candidate 1's monitoring session
    assert other_client.post("/api/monitoring/events", json={"session_id": session_id, "event_type": "tab_switch"}).status_code == 403
    assert other_client.get(f"/api/monitoring/events/{session_id}").status_code == 403


def test_monitoring_events_endpoints(client):
    session_id = setup_candidate_and_session(client, "telemetry@example.test", start=True)

    # Single event
    res1 = client.post("/api/monitoring/events", json={
        "session_id": session_id,
        "event_type": "tab_switch",
        "timestamp": "2026-08-30T10:00:00Z",
        "details": {"tab": 2},
    })
    assert res1.status_code == 201
    assert res1.get_json()["event"]["event_type"] == "tab_switch"

    # Batch events
    res2 = client.post("/api/monitoring/events", json={
        "session_id": session_id,
        "events": [
            {"event_type": "focus_loss", "timestamp": "2026-08-30T10:01:00Z"},
            {"event_type": "tab_switch", "timestamp": "2026-08-30T10:02:00Z"},
        ],
    })
    assert res2.status_code == 201
    assert len(res2.get_json()["events"]) == 3

    # Query events
    get_res = client.get(f"/api/monitoring/events/{session_id}")
    assert get_res.status_code == 200
    assert get_res.get_json()["count"] == 3

    # Query filtered by event_type
    filter_res = client.get(f"/api/monitoring/events/{session_id}?event_type=focus_loss")
    assert filter_res.status_code == 200
    assert filter_res.get_json()["count"] == 1


def test_face_absence_and_suspicious_endpoints(client):
    session_id = setup_candidate_and_session(client, "absence@example.test", start=True)

    # Log 4 tab switches
    for _ in range(4):
        client.post("/api/monitoring/events", json={"session_id": session_id, "event_type": "tab_switch"})

    # Post face absence interval
    res = client.post("/api/monitoring/face-absence", json={
        "session_id": session_id,
        "started_at": "2026-08-30T10:10:00Z",
        "ended_at": "2026-08-30T10:13:00Z",
        "duration_seconds": 180.0,
    })
    assert res.status_code == 201

    # Get face absence intervals
    res_abs = client.get(f"/api/monitoring/face-absence/{session_id}")
    assert res_abs.status_code == 200
    assert res_abs.get_json()["total_absence_duration_seconds"] == 180.0
    assert len(res_abs.get_json()["intervals"]) == 1

    # Get suspicious events
    res_susp = client.get(f"/api/monitoring/suspicious-events/{session_id}")
    assert res_susp.status_code == 200
    data = res_susp.get_json()
    assert data["tab_switches"] == 4
    assert data["face_absence_seconds"] == 180.0
    detected_types = {e["event_type"] for e in data["suspicious_events"]}
    assert "TAB_SWITCH_THRESHOLD_EXCEEDED" in detected_types
    assert "FACE_ABSENCE_THRESHOLD_EXCEEDED" in detected_types
