"""Administrative and proctoring authentication and dashboard routes."""

from functools import wraps
from flask import Blueprint, jsonify, request, session, g

from ..services.admin_service import (
    AdminAuthError,
    AdminValidationError,
    InvalidAdminCredentialsError,
    authenticate_admin,
    create_admin_user,
    get_admin_by_id,
    get_admin_sessions_list,
    get_admin_session_detail,
    get_dashboard_summary,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _payload():
    return request.get_json(silent=True) or {}


def require_admin_or_proctor(f):
    """Ensure the request is authenticated with an active PROCTOR or ADMIN session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_id = session.get("admin_id")
        if not admin_id:
            return jsonify({"error": "admin authentication required"}), 401

        admin = get_admin_by_id(admin_id)
        if not admin or not admin.get("is_active"):
            session.clear()
            return jsonify({"error": "administrative session invalid or inactive"}), 403

        g.admin = admin
        return f(*args, **kwargs)
    return decorated_function


def require_admin(f):
    """Ensure the request is authenticated with an active ADMIN session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_id = session.get("admin_id")
        if not admin_id:
            return jsonify({"error": "admin authentication required"}), 401

        admin = get_admin_by_id(admin_id)
        if not admin or not admin.get("is_active"):
            session.clear()
            return jsonify({"error": "administrative session invalid or inactive"}), 403

        if admin.get("role") != "ADMIN":
            return jsonify({"error": "administrator privilege required"}), 403

        g.admin = admin
        return f(*args, **kwargs)
    return decorated_function


def require_proctor(f):
    """Ensure the request is authenticated as either PROCTOR or ADMIN."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_id = session.get("admin_id")
        if not admin_id:
            return jsonify({"error": "proctor authentication required"}), 401

        admin = get_admin_by_id(admin_id)
        if not admin or not admin.get("is_active"):
            session.clear()
            return jsonify({"error": "administrative session invalid or inactive"}), 403

        if admin.get("role") not in ("PROCTOR", "ADMIN"):
            return jsonify({"error": "proctor privilege required"}), 403

        g.admin = admin
        return f(*args, **kwargs)
    return decorated_function


# --------------------------------------------------------------------------
# Authentication Endpoints
# --------------------------------------------------------------------------

@admin_bp.post("/auth/login")
def admin_login():
    """Authenticate an administrator or proctor."""
    data = _payload()
    email = data.get("email") or request.form.get("email")
    password = data.get("password") or request.form.get("password")

    try:
        admin = authenticate_admin(email, password)
    except AdminAuthError as err:
        return jsonify({"error": str(err)}), getattr(err, "status_code", 401)

    # Establish isolated administrative session
    session.clear()
    session["admin_id"] = admin["id"]
    session["admin_role"] = admin["role"]

    return jsonify({"authenticated": True, "admin": admin}), 200


@admin_bp.post("/auth/logout")
def admin_logout():
    """Terminate the current administrator or proctor session."""
    session.clear()
    return jsonify({"success": True, "authenticated": False}), 200


@admin_bp.get("/auth/me")
def admin_me():
    """Return the profile of the currently authenticated administrator or proctor."""
    admin_id = session.get("admin_id")
    if not admin_id:
        return jsonify({"authenticated": False}), 200

    admin = get_admin_by_id(admin_id)
    if not admin or not admin.get("is_active"):
        session.clear()
        return jsonify({"authenticated": False}), 200

    return jsonify({"authenticated": True, "admin": admin}), 200


# --------------------------------------------------------------------------
# Dashboard & Monitoring Endpoints
# --------------------------------------------------------------------------

@admin_bp.get("/dashboard/summary")
@require_admin_or_proctor
def dashboard_summary():
    """Return real-time counts and statistics for the proctor/admin dashboard."""
    summary = get_dashboard_summary()
    return jsonify({"summary": summary}), 200


@admin_bp.get("/sessions")
@require_admin_or_proctor
def sessions_list():
    """Return monitored examination sessions prioritized by integrity risk."""
    limit = request.args.get("limit", 50, type=int)
    sessions = get_admin_sessions_list(limit=limit)
    return jsonify({"sessions": sessions, "total": len(sessions)}), 200


@admin_bp.get("/sessions/<int:session_id>")
@require_admin_or_proctor
def session_detail(session_id: int):
    """Return detailed audit data and proctoring events for a single examination session."""
    detail = get_admin_session_detail(session_id)
    if not detail:
        return jsonify({"error": "examination session not found"}), 404
    return jsonify({"session": detail}), 200
