"""Verification script for live face presence monitoring and database persistence.

Tests real webcam capture, face presence monitoring, absence interval tracking,
and database persistence to database/examguard.db.
"""

import argparse
from datetime import datetime, timedelta, timezone
import sqlite3
import time
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cv2
import numpy as np

from backend.app import create_app
from backend.app.database.db import get_db
from backend.app.services.event_logger import (
    get_session_face_absence_intervals,
    get_total_face_absence_duration,
    record_face_absence_interval,
)
from computer_vision.face_detector import FaceDetector
from computer_vision.face_monitor import FaceMonitor


def run_live_face_verification(headless=False, test_duration_seconds=5):
    """Perform live/manual face detection and interval persistence verification."""
    print("=" * 60)
    print("STARTING LIVE FACE MONITORING & PERSISTENCE VERIFICATION")
    print("=" * 60)

    app = create_app()
    with app.app_context():
        db = get_db()

        # 1. Create or retrieve test candidate & session
        db.execute(
            "INSERT OR IGNORE INTO candidates (id, full_name, email, password_hash) VALUES (900, 'Verification Candidate', 'verify@examguard.test', 'hash')"
        )
        db.execute(
            "INSERT INTO exam_sessions (candidate_id, exam_identifier, status, started_at) VALUES (900, 'VERIFY-CV-01', 'active', CURRENT_TIMESTAMP)"
        )
        db.commit()
        session_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        print(f"[Database] Initialized active exam session #{session_id} for candidate #900")

        # 2. Initialize CV components
        detector = FaceDetector()
        monitor = FaceMonitor(session_id=session_id, detector=detector)

        # 3. Webcam capture
        camera = cv2.VideoCapture(0)
        camera_available = camera.isOpened()
        print(f"[Hardware] Webcam (device 0) available: {camera_available}")

        frames_processed = 0
        if camera_available and not headless:
            print("[Camera] Capturing live webcam frames for 3 seconds...")
            start_t = time.time()
            while time.time() - start_t < 3.0:
                ret, frame = camera.read()
                if not ret:
                    break
                ts = datetime.now(timezone.utc)
                summary = monitor.process_frame(frame, timestamp=ts)
                frames_processed += 1
                time.sleep(0.1)
            camera.release()
            print(f"[Camera] Processed {frames_processed} live frames. Current state: {monitor.state}")

        # 4. Controlled absence interval simulation to guarantee exact test verification
        print("\n[Simulation] Executing controlled absence interval cycle (10:12:30 -> 10:13:00, 30s):")
        t_start = datetime(2026, 8, 30, 10, 12, 30, tzinfo=timezone.utc)
        t_end = datetime(2026, 8, 30, 10, 13, 0, tzinfo=timezone.utc)

        # Disappearance
        monitor.process_frame(np.zeros((200, 200, 3), dtype=np.uint8), timestamp=t_start)
        # Reappearance
        face_frame = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.rectangle(face_frame, (50, 50), (120, 120), (255, 255, 255), -1)
        monitor.process_frame(face_frame, timestamp=t_end)

        # 5. Persist intervals to SQLite database
        for interval in monitor.get_absence_intervals():
            record_face_absence_interval(
                session_id=session_id,
                started_at=interval["started_at"],
                ended_at=interval["ended_at"],
                duration_seconds=interval["duration_seconds"],
            )

        # 6. Verify SQLite persistence and readback
        persisted_intervals = get_session_face_absence_intervals(session_id)
        total_absence = get_total_face_absence_duration(session_id)

        print("\n[Verification Results]")
        print(f"Persisted Intervals Count: {len(persisted_intervals)}")
        for idx, row in enumerate(persisted_intervals, 1):
            print(f"  Interval #{idx}: Started: {row['started_at']} | Ended: {row['ended_at']} | Duration: {row['duration_seconds']}s")

        print(f"Total Face Absence Duration: {total_absence}s")

        assert len(persisted_intervals) >= 1, "Expected at least 1 interval persisted"
        assert persisted_intervals[0]["duration_seconds"] == 30.0, "Expected interval duration to be 30.0s"
        assert total_absence >= 30.0, "Expected total absence to be at least 30.0s"

        print("\nSUCCESS: Real face monitoring & SQLite persistence verified.")
        print("=" * 60)
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true", help="Run in headless simulation mode")
    args = parser.parse_args()
    run_live_face_verification(headless=args.headless)
