"""Event Logger Service for Milestone 2.

Handles persistent telemetry storage, retrieval, and aggregation for active exam sessions.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional

from ..database.db import get_db
from ..models.event import FaceAbsenceInterval, MonitoringEvent
from .session_service import SessionAccessError, SessionNotFoundError


class EventLoggingError(Exception):
    status_code = 400


class EventValidationError(EventLoggingError):
    pass


class SessionStateError(EventLoggingError):
    status_code = 409


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_iso_timestamp(ts: Optional[Any]) -> str:
    if not ts:
        return _now_iso()
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()
    return str(ts)


def validate_session_for_monitoring(session_id: int, candidate_id: Optional[int] = None, require_active: bool = True) -> dict:
    """Validate that the session exists, belongs to candidate (if provided), and is active."""
    db = get_db()
    row = db.execute("SELECT * FROM exam_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        raise SessionNotFoundError("exam session was not found")
    if candidate_id is not None and row["candidate_id"] != candidate_id:
        raise SessionAccessError("you cannot access another candidate's session")
    if require_active and row["status"] != "active":
        raise SessionStateError(f"cannot log monitoring telemetry for a {row['status']} session")
    return dict(row)


def log_event(
    session_id: int,
    event_type: str,
    timestamp: Optional[Any] = None,
    details: Optional[Any] = None,
) -> Dict[str, Any]:
    """Persist a single monitoring event for an exam session."""
    event_type = (event_type or "").strip()
    if not event_type:
        raise EventValidationError("event_type is required")

    ts_str = _ensure_iso_timestamp(timestamp)
    details_str = json.dumps(details) if isinstance(details, (dict, list)) else (str(details) if details is not None else None)

    db = get_db()
    cursor = db.execute(
        "INSERT INTO monitoring_events (session_id, event_type, timestamp, details) VALUES (?, ?, ?, ?)",
        (session_id, event_type, ts_str, details_str),
    )
    db.commit()

    row = db.execute("SELECT * FROM monitoring_events WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return MonitoringEvent.from_row(row).to_dict()


def log_events_batch(session_id: int, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Persist a batch of monitoring events in a single transaction."""
    if not isinstance(events, list) or len(events) == 0:
        raise EventValidationError("events must be a non-empty list")

    records = []
    for item in events:
        event_type = (item.get("event_type") or "").strip()
        if not event_type:
            raise EventValidationError("event_type is required for all events in batch")
        ts_str = _ensure_iso_timestamp(item.get("timestamp"))
        details = item.get("details")
        details_str = json.dumps(details) if isinstance(details, (dict, list)) else (str(details) if details is not None else None)
        records.append((session_id, event_type, ts_str, details_str))

    db = get_db()
    cursor = db.cursor()
    cursor.executemany(
        "INSERT INTO monitoring_events (session_id, event_type, timestamp, details) VALUES (?, ?, ?, ?)",
        records,
    )
    db.commit()

    return get_session_events(session_id)


def get_session_events(session_id: int, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve chronologically ordered monitoring events for a session."""
    db = get_db()
    if event_type:
        rows = db.execute(
            "SELECT * FROM monitoring_events WHERE session_id = ? AND event_type = ? ORDER BY id ASC",
            (session_id, event_type),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM monitoring_events WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    return [MonitoringEvent.from_row(r).to_dict() for r in rows]


def count_session_events(session_id: int, event_type: str) -> int:
    """Return the exact count of a specific event type for a session from database records."""
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS count FROM monitoring_events WHERE session_id = ? AND event_type = ?",
        (session_id, event_type),
    ).fetchone()
    return int(row["count"]) if row else 0


def get_session_event_counts(session_id: int) -> Dict[str, int]:
    """Return aggregated event counts grouped by event_type for a session."""
    db = get_db()
    rows = db.execute(
        "SELECT event_type, COUNT(*) AS count FROM monitoring_events WHERE session_id = ? GROUP BY event_type",
        (session_id,),
    ).fetchall()
    return {row["event_type"]: row["count"] for row in rows}


def record_face_absence_interval(
    session_id: int,
    started_at: Any,
    ended_at: Optional[Any] = None,
    duration_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Persist a face absence interval with calculated duration."""
    start_str = _ensure_iso_timestamp(started_at)
    end_str = _ensure_iso_timestamp(ended_at) if ended_at else None

    if duration_seconds is None and end_str and start_str:
        try:
            start_dt = datetime.fromisoformat(start_str)
            end_dt = datetime.fromisoformat(end_str)
            duration_seconds = max(0.0, (end_dt - start_dt).total_seconds())
        except Exception:
            duration_seconds = 0.0

    duration_val = round(float(duration_seconds), 3) if duration_seconds is not None else None

    db = get_db()
    cursor = db.execute(
        """INSERT INTO face_absence_intervals (session_id, started_at, ended_at, duration_seconds)
           VALUES (?, ?, ?, ?)""",
        (session_id, start_str, end_str, duration_val),
    )
    db.commit()

    row = db.execute("SELECT * FROM face_absence_intervals WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return FaceAbsenceInterval.from_row(row).to_dict()


def get_session_face_absence_intervals(session_id: int) -> List[Dict[str, Any]]:
    """Retrieve all face absence intervals for a session."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM face_absence_intervals WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    return [FaceAbsenceInterval.from_row(r).to_dict() for r in rows]


def get_total_face_absence_duration(session_id: int) -> float:
    """Calculate total face absence duration across all recorded intervals for a session."""
    db = get_db()
    row = db.execute(
        "SELECT COALESCE(SUM(duration_seconds), 0.0) AS total_duration FROM face_absence_intervals WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return round(float(row["total_duration"]), 3) if row else 0.0

