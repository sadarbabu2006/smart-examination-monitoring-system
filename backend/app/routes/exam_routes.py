"""Candidate-owned exam session lifecycle routes."""

from flask import Blueprint, jsonify, request, session

from ..services.session_service import (
    SessionError,
    create_session,
    get_candidate_sessions,
    get_session,
    transition_session,
)

exam_bp = Blueprint("exam", __name__, url_prefix="/api/exam-sessions")


def _candidate_id():
    candidate_id = session.get("candidate_id")
    if not candidate_id:
        return None, (jsonify({"error": "authentication required"}), 401)
    return candidate_id, None


@exam_bp.get("")
def list_sessions():
    candidate_id, error = _candidate_id()
    if error:
        return error
    try:
        sessions = get_candidate_sessions(candidate_id)
        return jsonify({"sessions": sessions, "count": len(sessions)}), 200
    except SessionError as error:
        return jsonify({"error": str(error)}), error.status_code


@exam_bp.post("")
def create():
    candidate_id, error = _candidate_id()
    if error:
        return error
    try:
        value = create_session(candidate_id, (request.get_json(silent=True) or {}).get("exam_identifier"))
    except SessionError as error:
        return jsonify({"error": str(error)}), error.status_code
    return jsonify({"session": value}), 201


@exam_bp.get("/<int:session_id>")
def detail(session_id):
    candidate_id, error = _candidate_id()
    if error:
        return error
    try:
        return jsonify({"session": get_session(candidate_id, session_id)})
    except SessionError as error:
        return jsonify({"error": str(error)}), error.status_code


@exam_bp.post("/<int:session_id>/<action>")
def transition(session_id, action):
    candidate_id, error = _candidate_id()
    if error:
        return error
    try:
        return jsonify({"session": transition_session(candidate_id, session_id, action)})
    except SessionError as error:
        return jsonify({"error": str(error)}), error.status_code


@exam_bp.get("/<int:session_id>/integrity")
def get_session_integrity(session_id):
    candidate_id, error = _candidate_id()
    if error:
        return error

    try:
        session = get_session(candidate_id, session_id)
        from ..services.integrity_scoring import evaluate_and_persist_session_integrity, get_integrity_score

        score_data = get_integrity_score(session_id)
        if not score_data:
            # If not yet calculated, attempt to compute and persist now
            score_data = evaluate_and_persist_session_integrity(session_id)

        if not score_data:
            return jsonify({
                "session_id": session_id,
                "status": session["status"],
                "message": "integrity score not yet available for this session",
            }), 404

        breakdown = score_data.get("breakdown") or {}
        event_counts = breakdown.get("event_counts") or {}
        event_summary = {
            "tab_switch": event_counts.get("tab_switch", 0),
            "focus_loss": event_counts.get("focus_loss", 0),
            "window_blur": event_counts.get("window_blur", 0),
            "visibility_change": event_counts.get("visibility_change", 0),
            "multiple_faces": event_counts.get("multiple_faces", 0),
            "face_absence": 1 if (score_data.get("face_absence_seconds") or 0) > 0 else 0,
        }

        return jsonify({
            "session_id": session_id,
            "exam_identifier": session["exam_identifier"],
            "status": session["status"],
            "integrity_score": score_data["integrity_score"],
            "risk_level": score_data["risk_level"],
            "face_presence_ratio": score_data["face_presence_ratio"],
            "monitored_duration_seconds": score_data["monitored_duration_seconds"],
            "face_absence_seconds": score_data["face_absence_seconds"],
            "suspicious_event_count": score_data["suspicious_event_count"],
            "event_summary": event_summary,
            "breakdown": breakdown,
            "calculated_at": score_data["calculated_at"],
        }), 200

    except SessionError as err:
        return jsonify({"error": str(err)}), err.status_code
    except Exception as err:
        return jsonify({"error": f"Failed to retrieve integrity score: {str(err)}"}), 500

