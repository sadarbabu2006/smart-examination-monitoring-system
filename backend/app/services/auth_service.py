"""Candidate registration and password-based authentication."""

from werkzeug.security import check_password_hash, generate_password_hash

from ..database.db import get_db


class AuthError(Exception):
    status_code = 400


class ValidationError(AuthError):
    pass


class DuplicateCandidateError(AuthError):
    status_code = 409


class InvalidCredentialsError(AuthError):
    status_code = 401


def _candidate_public(row):
    return {
        "id": row["id"], "full_name": row["full_name"], "email": row["email"],
        "username": row["username"], "registration_photo_path": row["registration_photo_path"],
        "created_at": row["created_at"], "account_status": row["account_status"],
    }


def register_candidate(full_name, email, password, username=None, registration_photo_path=None):
    full_name, email = (full_name or "").strip(), (email or "").strip().lower()
    username = (username or "").strip() or None
    if not full_name or not email or not password:
        raise ValidationError("full_name, email, and password are required")
    if "@" not in email or len(email) > 254:
        raise ValidationError("a valid email address is required")
    if len(password) < 8:
        raise ValidationError("password must contain at least 8 characters")
    if username and len(username) > 80:
        raise ValidationError("username must not exceed 80 characters")

    db = get_db()
    if db.execute("SELECT 1 FROM candidates WHERE email = ? OR (? IS NOT NULL AND username = ?)",
                  (email, username, username)).fetchone():
        raise DuplicateCandidateError("an account with that email or username already exists")
    cursor = db.execute(
        """INSERT INTO candidates (full_name, email, username, password_hash, registration_photo_path)
           VALUES (?, ?, ?, ?, ?)""",
        (full_name, email, username, generate_password_hash(password), registration_photo_path),
    )
    db.commit()
    return get_candidate(cursor.lastrowid)


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
