"""Administrative user management, authentication, and proctoring dashboard services."""

import re
import sqlite3
from typing import Any, Dict, List, Optional
from werkzeug.security import check_password_hash, generate_password_hash

from ..database.db import get_db
from ..models.admin_user import AdminUser

SPECIAL_CHAR_REGEX = re.compile(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?~`]")


class AdminAuthError(Exception):
    status_code = 400


class AdminValidationError(AdminAuthError):
    status_code = 400


class DuplicateAdminError(AdminAuthError):
    status_code = 409


class InvalidAdminCredentialsError(AdminAuthError):
    status_code = 401


def validate_admin_password(password: str) -> None:
    """Validate administrative password complexity."""
    if not password or len(password) < 8:
        raise AdminValidationError("password must contain at least 8 characters")
    if not re.search(r"[A-Z]", password):
        raise AdminValidationError("password must contain at least one uppercase letter")
    if not re.search(r"\d", password):
        raise AdminValidationError("password must contain at least one number")
    if not SPECIAL_CHAR_REGEX.search(password):
        raise AdminValidationError("password must contain at least one special character")


def create_admin_user(
    full_name: str,
    email: str,
    password: str,
    role: str = "PROCTOR",
    is_active: bool = True,
) -> Dict[str, Any]:
    """Create a new administrator or proctor user."""
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()
    role = (role or "").strip().upper()

    if not full_name or not email or not password:
        raise AdminValidationError("full_name, email, and password are required")
    if "@" not in email or len(email) > 254:
        raise AdminValidationError("a valid email address is required")
    if role not in ("ADMIN", "PROCTOR"):
        raise AdminValidationError("role must be either 'ADMIN' or 'PROCTOR'")

    validate_admin_password(password)

    db = get_db()
    if db.execute("SELECT 1 FROM proctor_admins WHERE email = ?", (email,)).fetchone():
        raise DuplicateAdminError("an administrator or proctor with that email already exists")

    cursor = db.execute(
        """INSERT INTO proctor_admins (full_name, email, password_hash, role, is_active)
           VALUES (?, ?, ?, ?, ?)""",
        (full_name, email, generate_password_hash(password), role, 1 if is_active else 0),
    )
    db.commit()
    admin_id = cursor.lastrowid
    return get_admin_by_id(admin_id)


def get_admin_by_id(admin_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve an admin/proctor by ID."""
    row = get_db().execute("SELECT * FROM proctor_admins WHERE id = ?", (admin_id,)).fetchone()
    if not row:
        return None
    return AdminUser.from_row(row).to_dict()


def get_admin_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Retrieve an admin/proctor by email."""
    row = get_db().execute("SELECT * FROM proctor_admins WHERE email = ?", ((email or "").strip().lower(),)).fetchone()
    if not row:
        return None
    return AdminUser.from_row(row).to_dict()


def authenticate_admin(email: str, password: str) -> Dict[str, Any]:
    """Authenticate an administrator or proctor with email and password."""
    email = (email or "").strip().lower()
    if not email or not password:
        raise InvalidAdminCredentialsError("invalid administrative credentials")

    row = get_db().execute("SELECT * FROM proctor_admins WHERE email = ?", (email,)).fetchone()
    if not row:
        raise InvalidAdminCredentialsError("invalid administrative credentials")

    if not row["is_active"]:
        raise InvalidAdminCredentialsError("administrative account is inactive")

    if not check_password_hash(row["password_hash"], password):
        raise InvalidAdminCredentialsError("invalid administrative credentials")

    return AdminUser.from_row(row).to_dict()


def get_dashboard_summary() -> Dict[str, Any]:
    """Calculate live summary statistics from real database tables."""
    db = get_db()

    # Active examination sessions
    active_row = db.execute("SELECT COUNT(*) as cnt FROM exam_sessions WHERE status = 'active'").fetchone()
    active_count = active_row["cnt"] if active_row else 0

    # Submitted examination sessions
    submitted_row = db.execute("SELECT COUNT(*) as cnt FROM exam_sessions WHERE status = 'submitted'").fetchone()
    submitted_count = submitted_row["cnt"] if submitted_row else 0

    # High risk sessions evaluated by integrity engine
    high_risk_row = db.execute("SELECT COUNT(*) as cnt FROM integrity_scores WHERE risk_level = 'HIGH'").fetchone()
    high_risk_count = high_risk_row["cnt"] if high_risk_row else 0

    # Total monitored sessions
    total_row = db.execute("SELECT COUNT(*) as cnt FROM exam_sessions").fetchone()
    total_count = total_row["cnt"] if total_row else 0

    return {
        "active_sessions": active_count,
        "submitted_sessions": submitted_count,
        "high_risk_sessions": high_risk_count,
        "total_sessions": total_count,
    }


def get_admin_sessions_list(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve examination sessions prioritized by integrity risk (HIGH > MEDIUM > LOW > None)."""
    db = get_db()
    query = """
        SELECT
            s.id AS session_id,
            s.candidate_id,
            c.full_name AS candidate_name,
            c.email AS candidate_email,
            s.exam_identifier,
            s.status,
            s.started_at,
            s.ended_at,
            s.created_at,
            i.integrity_score,
            i.risk_level,
            i.face_presence_ratio,
            CASE
                WHEN i.risk_level = 'HIGH' THEN 1
                WHEN i.risk_level = 'MEDIUM' THEN 2
                WHEN i.risk_level = 'LOW' THEN 3
                WHEN s.status = 'active' THEN 4
                ELSE 5
            END AS priority_rank
        FROM exam_sessions s
        JOIN candidates c ON s.candidate_id = c.id
        LEFT JOIN integrity_scores i ON s.id = i.session_id
        ORDER BY priority_rank ASC, s.created_at DESC, s.id DESC
        LIMIT ?
    """
    rows = db.execute(query, (limit,)).fetchall()
    results = []
    for r in rows:
        results.append({
            "session_id": r["session_id"],
            "candidate_id": r["candidate_id"],
            "candidate_name": r["candidate_name"],
            "candidate_email": r["candidate_email"],
            "exam_identifier": r["exam_identifier"],
            "status": r["status"],
            "started_at": r["started_at"],
            "ended_at": r["ended_at"],
            "created_at": r["created_at"],
            "integrity_score": r["integrity_score"],
            "risk_level": r["risk_level"],
            "face_presence_ratio": r["face_presence_ratio"],
        })
    return results


def get_admin_session_detail(session_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve detailed session data including proctoring events and integrity audit."""
    db = get_db()
    row = db.execute(
        """SELECT s.*, c.full_name AS candidate_name, c.email AS candidate_email,
                  i.integrity_score, i.risk_level, i.face_presence_ratio,
                  i.monitored_duration_seconds, i.face_absence_seconds,
                  i.suspicious_event_count, i.breakdown, i.calculated_at
           FROM exam_sessions s
           JOIN candidates c ON s.candidate_id = c.id
           LEFT JOIN integrity_scores i ON s.id = i.session_id
           WHERE s.id = ?""",
        (session_id,)
    ).fetchone()

    if not row:
        return None

    import json
    breakdown_data = None
    if row["breakdown"]:
        try:
            breakdown_data = json.loads(row["breakdown"])
        except Exception:
            breakdown_data = None

    # Retrieve events
    events_rows = db.execute(
        "SELECT id, event_type, timestamp, details FROM monitoring_events WHERE session_id = ? ORDER BY timestamp ASC",
        (session_id,)
    ).fetchall()
    events = [dict(ev) for ev in events_rows]

    # Retrieve face absence intervals
    absence_rows = db.execute(
        "SELECT id, started_at, ended_at, duration_seconds FROM face_absence_intervals WHERE session_id = ? ORDER BY started_at ASC",
        (session_id,)
    ).fetchall()
    absence_intervals = [dict(a) for a in absence_rows]

    return {
        "session_id": row["id"],
        "candidate_id": row["candidate_id"],
        "candidate_name": row["candidate_name"],
        "candidate_email": row["candidate_email"],
        "exam_identifier": row["exam_identifier"],
        "status": row["status"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "created_at": row["created_at"],
        "integrity": {
            "score": row["integrity_score"],
            "risk_level": row["risk_level"],
            "face_presence_ratio": row["face_presence_ratio"],
            "monitored_duration_seconds": row["monitored_duration_seconds"],
            "face_absence_seconds": row["face_absence_seconds"],
            "suspicious_event_count": row["suspicious_event_count"],
            "breakdown": breakdown_data,
            "calculated_at": row["calculated_at"],
        } if row["integrity_score"] is not None else None,
        "events": events,
        "face_absence_intervals": absence_intervals,
    }


def seed_default_admin_if_empty() -> None:
    """Seed default administrator and proctor accounts if proctor_admins table is empty."""
    db = get_db()
    count_row = db.execute("SELECT COUNT(*) as cnt FROM proctor_admins").fetchone()
    if count_row and count_row["cnt"] == 0:
        create_admin_user(
            full_name="Lead Administrator",
            email="admin@examguard.test",
            password="Admin-ExamGuard-2026!",
            role="ADMIN",
            is_active=True,
        )
        create_admin_user(
            full_name="Staff Proctor",
            email="proctor@examguard.test",
            password="Proctor-ExamGuard-2026!",
            role="PROCTOR",
            is_active=True,
        )
