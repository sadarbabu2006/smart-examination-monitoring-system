"""Milestone 1 exam-session lifecycle business logic."""

from ..database.db import get_db


class SessionError(Exception):
    status_code = 400


class SessionNotFoundError(SessionError):
    status_code = 404


class SessionAccessError(SessionError):
    status_code = 403


class InvalidTransitionError(SessionError):
    status_code = 409


def _public(row):
    return {key: row[key] for key in ("id", "candidate_id", "exam_identifier", "status", "started_at", "ended_at", "created_at")}


def create_session(candidate_id, exam_identifier):
    exam_identifier = (exam_identifier or "").strip()
    if not exam_identifier:
        raise SessionError("exam_identifier is required")
    db = get_db()
    if not db.execute("SELECT 1 FROM candidates WHERE id = ?", (candidate_id,)).fetchone():
        raise SessionNotFoundError("candidate does not exist")
    cursor = db.execute("INSERT INTO exam_sessions (candidate_id, exam_identifier) VALUES (?, ?)",
                        (candidate_id, exam_identifier))
    db.commit()
    return get_session(candidate_id, cursor.lastrowid)


def get_session(candidate_id, session_id):
    row = get_db().execute("SELECT * FROM exam_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        raise SessionNotFoundError("exam session was not found")
    if row["candidate_id"] != candidate_id:
        raise SessionAccessError("you cannot access another candidate's session")
    return _public(row)


def transition_session(candidate_id, session_id, action):
    session = get_session(candidate_id, session_id)
    transitions = {
        ("scheduled", "start"): "active", ("active", "pause"): "paused",
        ("paused", "resume"): "active", ("active", "submit"): "submitted",
    }
    next_status = transitions.get((session["status"], action))
    if next_status is None:
        raise InvalidTransitionError(f"cannot {action} a {session['status']} session")
    db = get_db()
    if action == "start":
        db.execute("UPDATE exam_sessions SET status = ?, started_at = CURRENT_TIMESTAMP WHERE id = ?", (next_status, session_id))
        db.commit()
    elif action == "submit":
        db.execute("UPDATE exam_sessions SET status = ?, ended_at = CURRENT_TIMESTAMP WHERE id = ?", (next_status, session_id))
        db.commit()
        # Automatically and safely calculate and persist integrity score upon exam submission
        # This is retained on the backend for institutional proctoring/audit
        try:
            from .integrity_scoring import evaluate_and_persist_session_integrity
            evaluate_and_persist_session_integrity(session_id)
        except Exception as err:
            import logging
            logging.getLogger(__name__).error("Failed to compute integrity score on submit for session %s: %s",
                                              session_id, str(err))
    else:
        db.execute("UPDATE exam_sessions SET status = ? WHERE id = ?", (next_status, session_id))
        db.commit()
    return get_session(candidate_id, session_id)


def get_candidate_sessions(candidate_id):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM exam_sessions WHERE candidate_id = ? ORDER BY created_at DESC, id DESC",
        (candidate_id,)
    ).fetchall()
    return [_public(row) for row in rows]

