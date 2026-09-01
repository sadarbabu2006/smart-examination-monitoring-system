import pytest

from backend.app import create_app
from backend.app.database.db import get_db
from backend.app.services.event_logger import (
    log_event,
    record_face_absence_interval,
)
from backend.app.services.suspicious_detector import (
    SuspiciousThresholdConfig,
    detect_suspicious_events,
    get_monitoring_summary,
)


@pytest.fixture()
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE_PATH": str(tmp_path / "examguard.db"),
        "REGISTRATION_PHOTO_DIR": str(tmp_path / "photos"),
    })


@pytest.fixture()
def session_id(app):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO candidates (full_name, email, password_hash) VALUES (?, ?, ?)",
            ("Ada Candidate", "ada@example.test", "hash"),
        )
        cand_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        db.execute(
            "INSERT INTO exam_sessions (candidate_id, exam_identifier, status) VALUES (?, ?, 'active')",
            (cand_id, "EXAM-101"),
        )
        sess_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        db.commit()
        return sess_id


def test_no_suspicious_events_when_within_thresholds(app, session_id):
    with app.app_context():
        # 2 tab switches (threshold is 3)
        log_event(session_id, "tab_switch")
        log_event(session_id, "tab_switch")
        # 60 seconds face absence (threshold is 120)
        record_face_absence_interval(
            session_id,
            started_at="2026-08-30T10:00:00Z",
            ended_at="2026-08-30T10:01:00Z",
            duration_seconds=60.0,
        )

        suspicious = detect_suspicious_events(session_id)
        assert len(suspicious) == 0


def test_tab_switch_threshold_exceeded(app, session_id):
    with app.app_context():
        # Log 10 actual tab switch events
        for i in range(10):
            log_event(session_id, "tab_switch", details={"count": i + 1})

        suspicious = detect_suspicious_events(session_id)
        assert len(suspicious) == 1
        event = suspicious[0]
        assert event["event_type"] == "TAB_SWITCH_THRESHOLD_EXCEEDED"
        assert event["session_id"] == session_id
        assert event["observed"] == 10
        assert event["threshold"] == 3


def test_face_absence_threshold_exceeded(app, session_id):
    with app.app_context():
        # Total absence: 30s + 120s = 150s (threshold is 120s)
        record_face_absence_interval(
            session_id,
            started_at="2026-08-30T10:12:30Z",
            ended_at="2026-08-30T10:13:00Z",
            duration_seconds=30.0,
        )
        record_face_absence_interval(
            session_id,
            started_at="2026-08-30T10:25:10Z",
            ended_at="2026-08-30T10:27:10Z",
            duration_seconds=120.0,
        )

        suspicious = detect_suspicious_events(session_id)
        assert len(suspicious) == 1
        event = suspicious[0]
        assert event["event_type"] == "FACE_ABSENCE_THRESHOLD_EXCEEDED"
        assert event["session_id"] == session_id
        assert event["observed_duration"] == 150.0
        assert event["threshold"] == 120.0


def test_exact_boundary_conditions(app, session_id):
    with app.app_context():
        config = SuspiciousThresholdConfig(max_tab_switches=3)

        # 3 tab switches: exactly at threshold -> should NOT trigger
        for _ in range(3):
            log_event(session_id, "tab_switch")
        assert len(detect_suspicious_events(session_id, config)) == 0

        # 4 tab switches: exceeds threshold -> DOES trigger
        log_event(session_id, "tab_switch")
        suspicious = detect_suspicious_events(session_id, config)
        assert len(suspicious) == 1
        assert suspicious[0]["observed"] == 4


def test_multiple_suspicious_conditions_and_summary(app, session_id):
    with app.app_context():
        # 5 tab switches
        for _ in range(5):
            log_event(session_id, "tab_switch")
        # 4 focus loss events
        for _ in range(4):
            log_event(session_id, "focus_loss")
        # 1 multiple faces event
        log_event(session_id, "multiple_faces")
        # 180s face absence
        record_face_absence_interval(
            session_id,
            started_at="2026-08-30T10:00:00Z",
            ended_at="2026-08-30T10:03:00Z",
            duration_seconds=180.0,
        )

        summary = get_monitoring_summary(session_id)
        assert summary["session_id"] == session_id
        assert summary["tab_switches"] == 5
        assert summary["focus_loss_count"] == 4
        assert summary["multiple_faces_count"] == 1
        assert summary["face_absence_seconds"] == 180.0
        assert len(summary["absence_intervals"]) == 1

        types = {e["event_type"] for e in summary["suspicious_events"]}
        assert types == {
            "TAB_SWITCH_THRESHOLD_EXCEEDED",
            "FOCUS_LOSS_THRESHOLD_EXCEEDED",
            "FACE_ABSENCE_THRESHOLD_EXCEEDED",
            "MULTIPLE_FACES_DETECTED",
        }
