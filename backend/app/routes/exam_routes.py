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
