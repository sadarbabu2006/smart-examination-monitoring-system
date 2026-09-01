import pytest

from backend.app import create_app
from backend.app.database.db import get_db
from backend.app.services.event_logger import (
    EventValidationError,
    count_session_events,
    get_session_event_counts,
    get_session_events,
    get_session_face_absence_intervals,
    get_total_face_absence_duration,
    log_event,
    log_events_batch,
    record_face_absence_interval,
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


def test_log_single_event(app, session_id):
    with app.app_context():
        event = log_event(session_id, "tab_switch", timestamp="2026-08-30T10:15:00Z", details={"target": "browser_tab_2"})
        assert event["session_id"] == session_id
        assert event["event_type"] == "tab_switch"
        assert event["timestamp"] == "2026-08-30T10:15:00Z"
        assert event["details"] == {"target": "browser_tab_2"}

        events = get_session_events(session_id)
        assert len(events) == 1
        assert events[0]["id"] == event["id"]


def test_log_events_batch_and_counts(app, session_id):
    with app.app_context():
        batch = [
            {"event_type": "tab_switch", "timestamp": "2026-08-30T10:01:00Z"},
            {"event_type": "tab_switch", "timestamp": "2026-08-30T10:02:00Z"},
            {"event_type": "focus_loss", "timestamp": "2026-08-30T10:03:00Z"},
            {"event_type": "tab_switch", "timestamp": "2026-08-30T10:04:00Z"},
        ]
        events = log_events_batch(session_id, batch)
        assert len(events) == 4

        # Test counting actual tab switches
        tab_switches = count_session_events(session_id, "tab_switch")
        assert tab_switches == 3

        # Test counting focus loss
        focus_losses = count_session_events(session_id, "focus_loss")
        assert focus_losses == 1

        # Test group counts
        counts = get_session_event_counts(session_id)
        assert counts["tab_switch"] == 3
        assert counts["focus_loss"] == 1


def test_face_absence_intervals_and_total_calculation(app, session_id):
    with app.app_context():
        # First absence: 30 seconds
        int1 = record_face_absence_interval(
            session_id,
            started_at="2026-08-30T10:12:30Z",
            ended_at="2026-08-30T10:13:00Z",
            duration_seconds=30.0,
        )
        assert int1["duration_seconds"] == 30.0

        # Second absence: 120 seconds (computed automatically from timestamps)
        int2 = record_face_absence_interval(
            session_id,
            started_at="2026-08-30T10:25:10+00:00",
            ended_at="2026-08-30T10:27:10+00:00",
        )
        assert int2["duration_seconds"] == 120.0

        intervals = get_session_face_absence_intervals(session_id)
        assert len(intervals) == 2

        # Total absence: 150 seconds (2 mins 30 secs)
        total_duration = get_total_face_absence_duration(session_id)
        assert total_duration == 150.0


def test_event_validation_errors(app, session_id):
    with app.app_context():
        with pytest.raises(EventValidationError):
            log_event(session_id, "")

        with pytest.raises(EventValidationError):
            log_events_batch(session_id, [])

        with pytest.raises(EventValidationError):
            log_events_batch(session_id, [{"event_type": ""}])
