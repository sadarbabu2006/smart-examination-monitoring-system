"""Face Monitoring Engine for Milestone 2."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np

from .face_detector import FaceDetector


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _ensure_dt(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, str):
        dt = datetime.fromisoformat(ts)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


class FaceMonitor:
    """Monitors face presence over time, tracking absence intervals and detecting visual anomalies."""

    STATE_INITIAL = "initial"
    STATE_PRESENT = "present"
    STATE_ABSENT = "absent"

    def __init__(
        self,
        session_id: Optional[int] = None,
        detector: Optional[FaceDetector] = None,
        cascade_path: Optional[str] = None,
    ):
        self.session_id = session_id
        self.detector = detector or FaceDetector(cascade_path=cascade_path)
        self.state = self.STATE_INITIAL
        self.current_absence_start: Optional[datetime] = None
        self.absence_intervals: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.last_frame_timestamp: Optional[datetime] = None

    def process_frame(
        self,
        frame: np.ndarray,
        timestamp: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Process a single video frame.

        Args:
            frame: OpenCV image array.
            timestamp: Optional datetime or ISO string representing frame capture time.

        Returns:
            Dict summarizing frame processing and any generated state transitions/events.
        """
        current_time = _ensure_dt(timestamp)
        self.last_frame_timestamp = current_time

        face_boxes = self.detector.detect_faces(frame)
        face_count = len(face_boxes)
        is_present = face_count > 0

        new_events: List[Dict[str, Any]] = []

        if self.state == self.STATE_INITIAL:
            if is_present:
                self.state = self.STATE_PRESENT
                event = {
                    "event_type": "face_detected",
                    "session_id": self.session_id,
                    "timestamp": _to_iso(current_time),
                    "details": {"face_count": face_count, "bounding_boxes": face_boxes},
                }
                new_events.append(event)
                self.events.append(event)
            else:
                self.state = self.STATE_ABSENT
                self.current_absence_start = current_time
                event = {
                    "event_type": "face_absent",
                    "session_id": self.session_id,
                    "timestamp": _to_iso(current_time),
                    "details": {"face_count": 0, "status": "session_started_absent"},
                }
                new_events.append(event)
                self.events.append(event)

        elif self.state == self.STATE_PRESENT:
            if not is_present:
                self.state = self.STATE_ABSENT
                self.current_absence_start = current_time
                event = {
                    "event_type": "face_absent",
                    "session_id": self.session_id,
                    "timestamp": _to_iso(current_time),
                    "details": {"face_count": 0},
                }
                new_events.append(event)
                self.events.append(event)

        elif self.state == self.STATE_ABSENT:
            if is_present:
                self.state = self.STATE_PRESENT
                start_dt = self.current_absence_start or current_time
                duration = max(0.0, (current_time - start_dt).total_seconds())

                interval = {
                    "session_id": self.session_id,
                    "started_at": _to_iso(start_dt),
                    "ended_at": _to_iso(current_time),
                    "duration_seconds": round(duration, 3),
                }
                self.absence_intervals.append(interval)
                self.current_absence_start = None

                event = {
                    "event_type": "face_returned",
                    "session_id": self.session_id,
                    "timestamp": _to_iso(current_time),
                    "details": {
                        "face_count": face_count,
                        "absence_duration_seconds": round(duration, 3),
                        "started_at": _to_iso(start_dt),
                        "ended_at": _to_iso(current_time),
                    },
                }
                new_events.append(event)
                self.events.append(event)

        # Check for multiple faces anomaly
        if face_count > 1:
            multi_event = {
                "event_type": "multiple_faces",
                "session_id": self.session_id,
                "timestamp": _to_iso(current_time),
                "details": {"face_count": face_count, "bounding_boxes": face_boxes},
            }
            new_events.append(multi_event)
            self.events.append(multi_event)

        active_absence_duration = 0.0
        if self.state == self.STATE_ABSENT and self.current_absence_start:
            active_absence_duration = max(0.0, (current_time - self.current_absence_start).total_seconds())

        return {
            "session_id": self.session_id,
            "timestamp": _to_iso(current_time),
            "state": self.state,
            "is_present": is_present,
            "face_count": face_count,
            "bounding_boxes": face_boxes,
            "new_events": new_events,
            "active_absence_duration": round(active_absence_duration, 3),
            "total_absence_duration": self.get_total_absence_seconds(current_time),
        }

    def close_session(self, end_timestamp: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Close active monitoring session.

        If currently absent, closes the active interval using the end timestamp.
        """
        current_time = _ensure_dt(end_timestamp) if end_timestamp else (self.last_frame_timestamp or datetime.now(timezone.utc))
        if self.state == self.STATE_ABSENT and self.current_absence_start is not None:
            duration = max(0.0, (current_time - self.current_absence_start).total_seconds())
            interval = {
                "session_id": self.session_id,
                "started_at": _to_iso(self.current_absence_start),
                "ended_at": _to_iso(current_time),
                "duration_seconds": round(duration, 3),
            }
            self.absence_intervals.append(interval)
            self.current_absence_start = None

            event = {
                "event_type": "session_ended_absent",
                "session_id": self.session_id,
                "timestamp": _to_iso(current_time),
                "details": {
                    "absence_duration_seconds": round(duration, 3),
                    "started_at": interval["started_at"],
                    "ended_at": interval["ended_at"],
                },
            }
            self.events.append(event)

        return list(self.absence_intervals)

    def get_absence_intervals(self) -> List[Dict[str, Any]]:
        """Return a copy of completed absence intervals."""
        return list(self.absence_intervals)

    def get_total_absence_seconds(self, at_time: Optional[Any] = None) -> float:
        """Calculate total face absence duration across all recorded intervals."""
        total = sum(interval.get("duration_seconds", 0.0) for interval in self.absence_intervals)
        if self.state == self.STATE_ABSENT and self.current_absence_start is not None:
            now = _ensure_dt(at_time) if at_time else datetime.now(timezone.utc)
            total += max(0.0, (now - self.current_absence_start).total_seconds())
        return round(total, 3)

    def get_events(self) -> List[Dict[str, Any]]:
        """Return a copy of all recorded monitoring events."""
        return list(self.events)

