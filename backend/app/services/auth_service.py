"""Candidate registration and password-based authentication."""

from werkzeug.security import check_password_hash, generate_password_hash

import re

from ..database.db import get_db

SPECIAL_CHAR_REGEX = re.compile(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?~`]")
LOCAL_PART_REGEX = re.compile(r"^[a-zA-Z0-9_+\-]+(?:\.[a-zA-Z0-9_+\-]+)*$")

RECOGNIZED_EMAIL_DOMAINS = {
    "gmail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "yahoo.com",
    "yahoo.co.in",
    "icloud.com",
    "proton.me",
    "protonmail.com",
}

TEST_EMAIL_DOMAINS = {
    "example.test",
    "examguard.test",
    "test.com",
}

COMMON_PASSWORDS_BLACKLIST = {
    "password123", "password123!", "12345678", "12345678!", "admin123", "admin123!"
}


class AuthError(Exception):
    status_code = 400


class ValidationError(AuthError):
    pass


class DuplicateCandidateError(AuthError):
    status_code = 409


class InvalidCredentialsError(AuthError):
    status_code = 401


def get_allowed_email_domains(include_test_domains: bool = True) -> set:
    domains = set(RECOGNIZED_EMAIL_DOMAINS)
    if include_test_domains:
        try:
            from flask import current_app, has_app_context
            if has_app_context() and current_app.config.get("TESTING"):
                domains.update(TEST_EMAIL_DOMAINS)
        except Exception:
            pass
    return domains


def validate_email_address(email: str, allowed_domains: set = None) -> str:
    """Validate candidate email against strict ExamGuard syntax and recognized-provider allowlist.

    Requirements:
    - Exactly one @ character
    - Non-empty local part
    - Non-empty domain
    - No spaces
    - No consecutive dots
    - Local part cannot start or end with a dot
    - Domain must have valid dot-separated components
    - Domain must be present in the recognized-provider allowlist
    - Normalized by trimming whitespace and lowercasing
    """
    if not email or not isinstance(email, str):
        raise ValidationError("Please enter a valid email address.")
    trimmed = email.strip()
    if not trimmed or len(trimmed) > 254 or " " in trimmed:
        raise ValidationError("Please enter a valid email address.")
    if trimmed.count("@") != 1:
        raise ValidationError("Please enter a valid email address.")

    local_part, domain_part = trimmed.split("@")
    if not local_part or not domain_part:
        raise ValidationError("Please enter a valid email address.")
    if ".." in local_part or ".." in domain_part:
        raise ValidationError("Please enter a valid email address.")
    if local_part.startswith(".") or local_part.endswith("."):
        raise ValidationError("Please enter a valid email address.")
    if not LOCAL_PART_REGEX.match(local_part):
        raise ValidationError("Please enter a valid email address.")

    domain_part = domain_part.lower()
    if allowed_domains is None:
        allowed_domains = get_allowed_email_domains()

    if domain_part not in allowed_domains:
        raise ValidationError("Please enter a valid email address.")

    return f"{local_part.lower()}@{domain_part}"


def validate_password_requirements(password: str) -> None:
    if not password or len(password) < 8:
        raise ValidationError("password must contain at least 8 characters")
    if not re.search(r"[A-Z]", password):
        raise ValidationError("password must contain at least one uppercase letter")
    if not re.search(r"\d", password):
        raise ValidationError("password must contain at least one number")
    if not SPECIAL_CHAR_REGEX.search(password):
        raise ValidationError("password must contain at least one special character")
    lower = password.lower().strip()
    if lower in COMMON_PASSWORDS_BLACKLIST or lower.rstrip("!@#$%^&*()_+-=[]{};':\"|,.<>/?~`") in {"password123", "12345678", "admin123"}:
        raise ValidationError("password is too common or easily guessable")


def _candidate_public(row):
    return {
        "id": row["id"], "full_name": row["full_name"], "email": row["email"],
        "username": row["username"], "registration_photo_path": row["registration_photo_path"],
        "created_at": row["created_at"], "account_status": row["account_status"],
    }


def register_candidate(full_name, email, password, username=None, registration_photo_path=None):
    full_name = (full_name or "").strip()
    username = (username or "").strip() or None
    if not full_name or not email or not password:
        raise ValidationError("full_name, email, and password are required")
    normalized_email = validate_email_address(email)
    validate_password_requirements(password)
    if username and len(username) > 80:
        raise ValidationError("username must not exceed 80 characters")

    db = get_db()
    if db.execute("SELECT 1 FROM candidates WHERE email = ? OR (? IS NOT NULL AND username = ?)",
                  (normalized_email, username, username)).fetchone():
        raise DuplicateCandidateError("an account with that email or username already exists")
    cursor = db.execute(
        """INSERT INTO candidates (full_name, email, username, password_hash, registration_photo_path)
           VALUES (?, ?, ?, ?, ?)""",
        (full_name, normalized_email, username, generate_password_hash(password), registration_photo_path),
    )
    db.commit()
    return get_candidate(cursor.lastrowid)


def cleanup_invalid_candidate_registrations(db=None):
    """Safely and transactionally remove candidates with invalid registration data (e.g. invalid emails).

    Removes exclusively candidate-owned records (exam_sessions, monitoring_events,
    face_absence_intervals, integrity_scores, registration photos) respecting foreign keys.
    Preserves valid candidates, admin/proctor accounts, and unrelated sessions.
    Safe and idempotent.
    """
    from pathlib import Path
    if db is None:
        db = get_db()

    candidates = db.execute("SELECT id, full_name, email, registration_photo_path FROM candidates").fetchall()
    removed_candidates = []

    for candidate in candidates:
        email = candidate["email"]
        is_valid = bool(email and isinstance(email, str) and EMAIL_REGEX.match(email.strip()))
        if not is_valid:
            cand_id = candidate["id"]

            # Find candidate-owned exam sessions
            sessions = db.execute(
                "SELECT id FROM exam_sessions WHERE candidate_id = ?", (cand_id,)
            ).fetchall()

            for session_row in sessions:
                sess_id = session_row["id"]
                db.execute("DELETE FROM integrity_scores WHERE session_id = ?", (sess_id,))
                db.execute("DELETE FROM face_absence_intervals WHERE session_id = ?", (sess_id,))
                db.execute("DELETE FROM monitoring_events WHERE session_id = ?", (sess_id,))

            db.execute("DELETE FROM exam_sessions WHERE candidate_id = ?", (cand_id,))

            # Safely remove candidate photo if present
            photo_path = candidate["registration_photo_path"]
            if photo_path:
                try:
                    p = Path(photo_path)
                    if p.is_file() and "registration_photos" in p.parts:
                        p.unlink(missing_ok=True)
                except Exception:
                    pass

            db.execute("DELETE FROM candidates WHERE id = ?", (cand_id,))
            removed_candidates.append({
                "id": cand_id,
                "full_name": candidate["full_name"],
                "email": candidate["email"],
            })

    if removed_candidates:
        db.commit()

    remaining_count = db.execute("SELECT COUNT(*) as cnt FROM candidates").fetchone()["cnt"]
    return {
        "removed_count": len(removed_candidates),
        "removed_candidates": removed_candidates,
        "preserved_count": remaining_count,
    }


def get_candidate(candidate_id):
    row = get_db().execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    return _candidate_public(row) if row else None


def authenticate_candidate(email_or_username, password):
    identity = (email_or_username or "").strip()
    if not identity or not password:
        raise InvalidCredentialsError("invalid credentials")
    row = get_db().execute(
        "SELECT * FROM candidates WHERE email = ? OR username = ?", (identity.lower(), identity)
    ).fetchone()
    if not row or row["account_status"] != "active" or not check_password_hash(row["password_hash"], password):
        raise InvalidCredentialsError("invalid credentials")
    return _candidate_public(row)


def update_registration_photo(candidate_id, photo_path):
    db = get_db()
    if not db.execute("SELECT 1 FROM candidates WHERE id = ?", (candidate_id,)).fetchone():
        raise ValidationError("candidate does not exist")
    db.execute("UPDATE candidates SET registration_photo_path = ? WHERE id = ?", (photo_path, candidate_id))
    db.commit()
    return get_candidate(candidate_id)
