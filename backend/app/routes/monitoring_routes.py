"""Monitoring and Telemetry Routes for Milestone 2."""

from flask import Blueprint, jsonify, request, session

from ..services.event_logger import (
    EventLoggingError,
    get_session_events,
    get_session_face_absence_intervals,
    get_total_face_absence_duration,
    log_event,
    log_events_batch,
    record_face_absence_interval,
    validate_session_for_monitoring,
)
from ..services.session_service import SessionError
from ..services.suspicious_detector import (
    SuspiciousThresholdConfig,
    detect_suspicious_events,
    get_monitoring_summary,
)

monitoring_bp = Blueprint("monitoring", __name__, url_prefix="/api/monitoring")


def _candidate_id():
    candidate_id = session.get("candidate_id")
    if not candidate_id:
        return None, (jsonify({"error": "authentication required"}), 401)
    return candidate_id, None


def _payload():
    return request.get_json(silent=True) or {}


@monitoring_bp.post("/events")
def post_events():
    candidate_id, error = _candidate_id()
    if error:
        return error

    data = _payload()
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    try:
        validate_session_for_monitoring(session_id, candidate_id=candidate_id, require_active=True)

        if "events" in data and isinstance(data["events"], list):
            events = log_events_batch(session_id, data["events"])
            return jsonify({"session_id": session_id, "events": events}), 201
        else:
            event_type = data.get("event_type")
            timestamp = data.get("timestamp")
            details = data.get("details")
            event = log_event(session_id, event_type, timestamp=timestamp, details=details)
            return jsonify({"session_id": session_id, "event": event}), 201

    except (EventLoggingError, SessionError) as err:
        return jsonify({"error": str(err)}), getattr(err, "status_code", 400)


@monitoring_bp.get("/events/<int:session_id>")
def get_events(session_id):
    candidate_id, error = _candidate_id()
    if error:
        return error

    try:
        validate_session_for_monitoring(session_id, candidate_id=candidate_id, require_active=False)
        event_type = request.args.get("event_type")
        events = get_session_events(session_id, event_type=event_type)
        return jsonify({"session_id": session_id, "events": events, "count": len(events)}), 200
    except (EventLoggingError, SessionError) as err:
        return jsonify({"error": str(err)}), getattr(err, "status_code", 400)


@monitoring_bp.post("/face-absence")
def post_face_absence():
    candidate_id, error = _candidate_id()
    if error:
        return error

    data = _payload()
    session_id = data.get("session_id")
    started_at = data.get("started_at")
    ended_at = data.get("ended_at")
    duration_seconds = data.get("duration_seconds")

    if not session_id or not started_at:
        return jsonify({"error": "session_id and started_at are required"}), 400

    try:
        validate_session_for_monitoring(session_id, candidate_id=candidate_id, require_active=True)
        interval = record_face_absence_interval(
            session_id=session_id,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
        )
        return jsonify({"session_id": session_id, "interval": interval}), 201
    except (EventLoggingError, SessionError) as err:
        return jsonify({"error": str(err)}), getattr(err, "status_code", 400)


@monitoring_bp.get("/face-absence/<int:session_id>")
def get_face_absence(session_id):
    candidate_id, error = _candidate_id()
    if error:
        return error

    try:
        validate_session_for_monitoring(session_id, candidate_id=candidate_id, require_active=False)
        intervals = get_session_face_absence_intervals(session_id)
        total_duration = get_total_face_absence_duration(session_id)
        return jsonify({
            "session_id": session_id,
            "intervals": intervals,
            "total_absence_duration_seconds": total_duration,
        }), 200
    except (EventLoggingError, SessionError) as err:
        return jsonify({"error": str(err)}), getattr(err, "status_code", 400)


@monitoring_bp.get("/suspicious-events/<int:session_id>")
def get_suspicious(session_id):
    candidate_id, error = _candidate_id()
    if error:
        return error

    try:
        validate_session_for_monitoring(session_id, candidate_id=candidate_id, require_active=False)

        # Parse optional query thresholds
        config = SuspiciousThresholdConfig()
        if "max_tab_switches" in request.args:
            config.max_tab_switches = int(request.args["max_tab_switches"])
        if "max_face_absence_seconds" in request.args:
            config.max_face_absence_seconds = float(request.args["max_face_absence_seconds"])
        if "max_focus_loss_events" in request.args:
            config.max_focus_loss_events = int(request.args["max_focus_loss_events"])

        summary = get_monitoring_summary(session_id, config=config)
        return jsonify(summary), 200
    except (EventLoggingError, SessionError) as err:
        return jsonify({"error": str(err)}), getattr(err, "status_code", 400)


# In-memory session monitor store
_session_monitors = {}
_detector = None


def _get_detector():
    global _detector
    if _detector is None:
        from computer_vision.face_detector import FaceDetector
        _detector = FaceDetector()
    return _detector


def _decode_frame(frame_data):
    import base64
    import cv2
    import numpy as np

    if not frame_data:
        return None
    if "," in frame_data:
        frame_data = frame_data.split(",", 1)[1]
    raw_bytes = base64.b64decode(frame_data)
    np_arr = np.frombuffer(raw_bytes, np.uint8)
    return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)


@monitoring_bp.post("/verify-frame")
def verify_frame():
    data = _payload()
    frame_b64 = data.get("frame")
    if not frame_b64:
        return jsonify({"error": "frame data is required"}), 400

    try:
        frame = _decode_frame(frame_b64)
        if frame is None:
            return jsonify({"error": "invalid image frame data"}), 400

        detector = _get_detector()
        boxes = detector.detect_faces(frame)
        count = len(boxes)
        status = "face_detected" if count == 1 else ("multiple_faces" if count > 1 else "no_face")

        return jsonify({
            "face_count": count,
            "status": status,
            "bounding_boxes": boxes,
            "verified": count == 1,
        }), 200
    except Exception as err:
        return jsonify({"error": f"verification failed: {str(err)}"}), 500


@monitoring_bp.post("/process-frame")
def process_frame():
    from computer_vision.face_monitor import FaceMonitor

    candidate_id, error = _candidate_id()
    if error:
        return error

    data = _payload()
    session_id = data.get("session_id")
    frame_b64 = data.get("frame")

    if not session_id or not frame_b64:
        return jsonify({"error": "session_id and frame are required"}), 400

    try:
        validate_session_for_monitoring(session_id, candidate_id=candidate_id, require_active=True)
        frame = _decode_frame(frame_b64)
        if frame is None:
            return jsonify({"error": "invalid image frame data"}), 400

        if session_id not in _session_monitors:
            _session_monitors[session_id] = FaceMonitor(session_id=session_id, detector=_get_detector())

        monitor = _session_monitors[session_id]
        prev_interval_count = len(monitor.absence_intervals)
        res = monitor.process_frame(frame)

        # If an interval was closed, persist to SQLite
        if len(monitor.absence_intervals) > prev_interval_count:
            latest_interval = monitor.absence_intervals[-1]
            record_face_absence_interval(
                session_id=session_id,
                started_at=latest_interval["started_at"],
                ended_at=latest_interval["ended_at"],
                duration_seconds=latest_interval["duration_seconds"],
            )

        # Log any newly emitted events
        for ev in res.get("new_events", []):
            log_event(
                session_id=session_id,
                event_type=ev["event_type"],
                timestamp=ev.get("timestamp"),
                details=ev.get("details"),
            )

        return jsonify({
            "session_id": session_id,
            "state": res["state"],
            "is_present": res["is_present"],
            "face_count": res["face_count"],
            "bounding_boxes": res["bounding_boxes"],
            "active_absence_duration": res["active_absence_duration"],
            "total_absence_duration": res["total_absence_duration"],
            "new_events": res["new_events"],
        }), 200
    except (EventLoggingError, SessionError) as err:
        return jsonify({"error": str(err)}), getattr(err, "status_code", 400)
    except Exception as err:
        return jsonify({"error": f"frame processing failed: {str(err)}"}), 500


