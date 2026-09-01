import sqlite3
import pytest

from backend.app import create_app
from backend.app.database.db import get_db, init_db


@pytest.fixture()
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE_PATH": str(tmp_path / "examguard.db"),
        "REGISTRATION_PHOTO_DIR": str(tmp_path / "photos"),
    })


def test_monitoring_schema_and_tables(app):
    with app.app_context():
        db = get_db()
        tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"candidates", "exam_sessions", "monitoring_events", "face_absence_intervals"}.issubset(tables)


def test_foreign_key_enforcement_for_monitoring_events(app):
    with app.app_context():
        db = get_db()
        # Should fail because session 999 does not exist
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO monitoring_events (session_id, event_type) VALUES (?, ?)",
                (999, "tab_switch"),
            )


def test_foreign_key_enforcement_for_face_absence_intervals(app):
    with app.app_context():
        db = get_db()
        # Should fail because session 999 does not exist
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO face_absence_intervals (session_id, started_at) VALUES (?, ?)",
                (999, "2026-08-30T10:00:00Z"),
            )


def test_safe_repeatable_database_initialization(app):
    with app.app_context():
        db = get_db()
        # Insert a candidate and session
        db.execute(
            "INSERT INTO candidates (full_name, email, password_hash) VALUES (?, ?, ?)",
            ("Test Candidate", "test@example.com", "hash"),
        )
        candidate_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        db.execute(
            "INSERT INTO exam_sessions (candidate_id, exam_identifier) VALUES (?, ?)",
            (candidate_id, "EXAM-101"),
        )
        session_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        db.execute(
            "INSERT INTO monitoring_events (session_id, event_type) VALUES (?, ?)",
            (session_id, "tab_switch"),
        )
        db.commit()

        # Re-run init_db
        init_db()

        # Check that data is completely preserved
        events = db.execute("SELECT * FROM monitoring_events WHERE session_id = ?", (session_id,)).fetchall()
        assert len(events) == 1
        assert events[0]["event_type"] == "tab_switch"
