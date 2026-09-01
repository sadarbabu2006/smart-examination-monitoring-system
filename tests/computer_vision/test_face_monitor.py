from datetime import datetime, timezone
import numpy as np
import pytest

from computer_vision.face_detector import FaceDetector, FaceDetectorError
from computer_vision.face_monitor import FaceMonitor


class MockFaceDetector:
    """Mock detector for deterministic state machine testing."""
    def __init__(self, face_count_to_return=1):
        self.face_count = face_count_to_return

    def detect_faces(self, frame, **kwargs):
        if frame is None or getattr(frame, "size", 0) == 0:
            raise ValueError("Invalid frame")
        if self.face_count == 0:
            return []
        return [(10 * i, 10 * i, 50, 50) for i in range(self.face_count)]

    def count_faces(self, frame):
        return len(self.detect_faces(frame))

    def is_face_present(self, frame):
        return self.count_faces(frame) > 0


def test_face_detector_haar_cascade_initialization_and_validation():
    detector = FaceDetector()
    assert detector.classifier is not None
    assert not detector.classifier.empty()

    # Blank frame returns 0 faces with Haar cascade
    blank = np.zeros((200, 200, 3), dtype=np.uint8)
    assert detector.count_faces(blank) == 0
    assert not detector.is_face_present(blank)

    # Frame validation errors
    with pytest.raises(ValueError):
        detector.detect_faces(None)

    with pytest.raises(ValueError):
        detector.detect_faces(np.array([]))


def test_face_monitor_presence_and_absence_transitions():
    detector = MockFaceDetector(face_count_to_return=1)
    monitor = FaceMonitor(session_id=1, detector=detector)
    t0 = datetime(2026, 8, 30, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 30, 10, 0, 30, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 30, 10, 1, 0, tzinfo=timezone.utc)

    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)

    # Frame 1: Face present at 10:00:00
    res1 = monitor.process_frame(dummy_frame, timestamp=t0)
    assert res1["state"] == "present"
    assert res1["is_present"] is True
    assert res1["face_count"] == 1
    assert monitor.get_total_absence_seconds() == 0.0

    # Frame 2: Face disappears at 10:00:30 (absence begins)
    detector.face_count = 0
    res2 = monitor.process_frame(dummy_frame, timestamp=t1)
    assert res2["state"] == "absent"
    assert res2["is_present"] is False
    assert any(e["event_type"] == "face_absent" for e in res2["new_events"])

    # Frame 3: Face returns at 10:01:00 (absence duration: 30s)
    detector.face_count = 1
    res3 = monitor.process_frame(dummy_frame, timestamp=t2)
    assert res3["state"] == "present"
    assert res3["is_present"] is True

    intervals = monitor.get_absence_intervals()
    assert len(intervals) == 1
    assert intervals[0]["duration_seconds"] == 30.0
    assert monitor.get_total_absence_seconds() == 30.0


def test_face_monitor_multiple_absence_intervals():
    detector = MockFaceDetector(face_count_to_return=1)
    monitor = FaceMonitor(session_id=2, detector=detector)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    # 1. Start with face at 10:00:00
    monitor.process_frame(frame, timestamp=datetime(2026, 8, 30, 10, 0, 0, tzinfo=timezone.utc))

    # 2. Absence 1: 10:12:30 -> 10:13:00 (30 seconds)
    detector.face_count = 0
    monitor.process_frame(frame, timestamp=datetime(2026, 8, 30, 10, 12, 30, tzinfo=timezone.utc))
    detector.face_count = 1
    monitor.process_frame(frame, timestamp=datetime(2026, 8, 30, 10, 13, 0, tzinfo=timezone.utc))

    # 3. Absence 2: 10:25:10 -> 10:27:10 (120 seconds / 2 minutes)
    detector.face_count = 0
    monitor.process_frame(frame, timestamp=datetime(2026, 8, 30, 10, 25, 10, tzinfo=timezone.utc))
    detector.face_count = 1
    monitor.process_frame(frame, timestamp=datetime(2026, 8, 30, 10, 27, 10, tzinfo=timezone.utc))

    intervals = monitor.get_absence_intervals()
    assert len(intervals) == 2
    assert intervals[0]["duration_seconds"] == 30.0
    assert intervals[1]["duration_seconds"] == 120.0

    # Total absence: 150 seconds (2 mins 30 secs)
    assert monitor.get_total_absence_seconds() == 150.0


def test_face_monitor_close_session_while_absent():
    detector = MockFaceDetector(face_count_to_return=1)
    monitor = FaceMonitor(session_id=3, detector=detector)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    # Starts present at 10:00:00
    monitor.process_frame(frame, timestamp=datetime(2026, 8, 30, 10, 0, 0, tzinfo=timezone.utc))

    # Disappears at 10:10:00
    detector.face_count = 0
    monitor.process_frame(frame, timestamp=datetime(2026, 8, 30, 10, 10, 0, tzinfo=timezone.utc))

    # Session ends at 10:15:00 while candidate is still absent (300 seconds)
    intervals = monitor.close_session(end_timestamp=datetime(2026, 8, 30, 10, 15, 0, tzinfo=timezone.utc))
    assert len(intervals) == 1
    assert intervals[0]["duration_seconds"] == 300.0
    assert monitor.get_total_absence_seconds() == 300.0


def test_face_monitor_multiple_faces_event():
    detector = MockFaceDetector(face_count_to_return=2)
    monitor = FaceMonitor(session_id=4, detector=detector)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    res = monitor.process_frame(frame, timestamp=datetime(2026, 8, 30, 10, 0, 0, tzinfo=timezone.utc))
    assert res["face_count"] == 2
    assert any(e["event_type"] == "multiple_faces" for e in res["new_events"])

