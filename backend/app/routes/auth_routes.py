"""Candidate registration, login, and registration-photo routes."""

import base64
from pathlib import Path
import cv2
from flask import Blueprint, current_app, jsonify, request, session
import numpy as np

from ..services.auth_service import (
    AuthError,
    authenticate_candidate,
    get_candidate,
    register_candidate,
    update_registration_photo,
)
from computer_vision.registration_photo import (
    PhotoCaptureError,
    capture_registration_photo,
    save_registration_frame,
    validate_registration_photo_path,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _payload():
    return request.get_json(silent=True) or {}


@auth_bp.post("/register")
def register():
    data = _payload()
    # Support both JSON payload and multipart/form-data
    full_name = data.get("full_name") or request.form.get("full_name")
    email = data.get("email") or request.form.get("email")
    password = data.get("password") or request.form.get("password")
    username = data.get("username") or request.form.get("username")

    photo_path = data.get("registration_photo_path")
    photo_base64 = data.get("photo_base64") or data.get("registration_photo_data")
    photo_file = request.files.get("registration_photo") if request.files else None

    storage_dir = current_app.config["REGISTRATION_PHOTO_DIR"]

    try:
        if photo_file and photo_file.filename:
            raw_bytes = photo_file.read()
            if not raw_bytes:
                raise PhotoCaptureError("uploaded registration photo file is empty")
            np_arr = np.frombuffer(raw_bytes, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is None:
                raise PhotoCaptureError("uploaded file is not a valid image format")
            photo_path = save_registration_frame(frame, storage_dir)

        elif photo_base64:
            if "," in photo_base64:
                photo_base64 = photo_base64.split(",", 1)[1]
            raw_bytes = base64.b64decode(photo_base64)
            np_arr = np.frombuffer(raw_bytes, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is None:
                raise PhotoCaptureError("uploaded image data could not be decoded")
            photo_path = save_registration_frame(frame, storage_dir)

        elif data.get("capture_photo"):
            photo_path = capture_registration_photo(storage_dir)

        elif photo_path:
            photo_path = validate_registration_photo_path(photo_path, storage_dir)

        candidate = register_candidate(full_name, email, password, username, photo_path)
    except (AuthError, PhotoCaptureError) as error:
        return jsonify({"error": str(error)}), getattr(error, "status_code", 400)

    return jsonify({"candidate": candidate}), 201


@auth_bp.post("/login")
def login():
    data = _payload()
    identity = data.get("email") or data.get("username") or request.form.get("email") or request.form.get("username")
    password = data.get("password") or request.form.get("password")
    try:
        candidate = authenticate_candidate(identity, password)
    except AuthError as error:
        return jsonify({"error": str(error)}), error.status_code
    session.clear()
    session["candidate_id"] = candidate["id"]
    return jsonify({"candidate": candidate, "authenticated": True})


@auth_bp.get("/me")
def me():
    candidate_id = session.get("candidate_id")
    if not candidate_id:
        return jsonify({"authenticated": False}), 200
    candidate = get_candidate(candidate_id)
    if not candidate:
        session.clear()
        return jsonify({"authenticated": False}), 200
    return jsonify({"authenticated": True, "candidate": candidate}), 200


@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"success": True, "authenticated": False}), 200


@auth_bp.get("/photo")
def get_photo():
    candidate_id = session.get("candidate_id")
    if not candidate_id:
        return jsonify({"error": "authentication required"}), 401
    candidate = get_candidate(candidate_id)
    if not candidate or not candidate.get("registration_photo_path"):
        return jsonify({"error": "photo not found"}), 404
    photo_path = Path(candidate["registration_photo_path"])
    if not photo_path.is_file():
        return jsonify({"error": "photo file missing"}), 404
    from flask import send_file
    return send_file(str(photo_path), mimetype="image/jpeg")


@auth_bp.post("/registration-photo")
def registration_photo():
    candidate_id = session.get("candidate_id")
    if not candidate_id:
        return jsonify({"error": "authentication required"}), 401
    try:
        path = capture_registration_photo(current_app.config["REGISTRATION_PHOTO_DIR"])
        candidate = update_registration_photo(candidate_id, path)
    except (AuthError, PhotoCaptureError) as error:
        return jsonify({"error": str(error)}), getattr(error, "status_code", 400)
    return jsonify({"candidate": candidate})


