"""Interactive Live Webcam Proctoring Runner for Milestone 2.

Captures real-time video frames from the candidate's webcam, monitors face presence,
tracks absence intervals upon departure and return, and persists intervals to SQLite.

Usage:
    python scripts/run_live_webcam_proctoring.py --duration 30
"""

import argparse
from datetime import datetime, timezone
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cv2
from backend.app import create_app
from backend.app.database.db import get_db
from backend.app.services.event_logger import (
    get_session_face_absence_intervals,
    get_total_face_absence_duration,
    record_face_absence_interval,
)
from computer_vision.face_detector import FaceDetector
from computer_vision.face_monitor import FaceMonitor


def run_live_webcam_proctor(duration_seconds=30, camera_index=0):
    print("=" * 70)
    print("LIVE WEBCAM PROCTORING SESSION (REAL HARDWARE MONITORING)")
    print("=" * 70)

    app = create_app()
    with app.app_context():
        db = get_db()

        # 1. Setup candidate & active exam session in SQLite
        db.execute(
            "INSERT OR IGNORE INTO candidates (id, full_name, email, password_hash) "
            "VALUES (1001, 'Live Proctor Candidate', 'live_candidate@examguard.test', 'scrypt:test')"
        )
        db.execute(
            "INSERT INTO exam_sessions (candidate_id, exam_identifier, status, started_at) "
            "VALUES (1001, 'LIVE-MANUAL-VERIFICATION', 'active', CURRENT_TIMESTAMP)"
        )
        db.commit()
        session_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        print(f"[Session] Started active exam session #{session_id} for Candidate #1001")

        # 2. Initialize camera and detector
        camera = cv2.VideoCapture(camera_index)
        if not camera.isOpened():
            print("[ERROR] Could not open webcam device. Check camera permissions.")
            return False

        detector = FaceDetector()
        monitor = FaceMonitor(session_id=session_id, detector=detector)
        print(f"[Camera] Webcam initialized (device {camera_index}).")
        print(f"[Instructions] Proctoring will run for {duration_seconds} seconds.")
        print("  - Keep your face in frame.")
        print("  - Step out / hide face for 10-15 seconds.")
        print("  - Step back in frame.")
        print("  - The system will detect and persist the absence interval in SQLite.")
        print("-" * 70)

        start_time = time.time()
        last_logged_intervals_count = 0
        frame_idx = 0

        try:
            while (time.time() - start_time) < duration_seconds:
                ret, frame = camera.read()
                if not ret:
                    print("[Warning] Could not read frame from camera.")
                    time.sleep(0.1)
                    continue

                frame_idx += 1
                now = datetime.now(timezone.utc)
                summary = monitor.process_frame(frame, timestamp=now)

                # Check if a new interval was closed
                current_intervals = monitor.get_absence_intervals()
                if len(current_intervals) > last_logged_intervals_count:
                    for i in range(last_logged_intervals_count, len(current_intervals)):
                        closed_int = current_intervals[i]
                        record_face_absence_interval(
                            session_id=session_id,
                            started_at=closed_int["started_at"],
                            ended_at=closed_int["ended_at"],
                            duration_seconds=closed_int["duration_seconds"],
                        )
                        print(
                            f"\n>>> [INTERVAL RECORDED TO SQLITE] Started: {closed_int['started_at']} | "
                            f"Ended: {closed_int['ended_at']} | Duration: {closed_int['duration_seconds']}s"
                        )
                    last_logged_intervals_count = len(current_intervals)

                # Periodic console update (every ~1s)
                if frame_idx % 10 == 0:
                    elapsed = int(time.time() - start_time)
                    active_dur = summary["active_absence_duration"]
                    print(
                        f"[{elapsed:02d}s/{duration_seconds}s] State: {summary['state'].upper():<7} | "
                        f"Faces: {summary['face_count']} | Active Absence: {active_dur:.1f}s | "
                        f"Total Absence: {summary['total_absence_duration']:.1f}s"
                    )

                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\n[Proctoring] Stopped by user.")

        finally:
            camera.release()
            print("-" * 70)

            # Close any trailing absence interval if still absent at session end
            end_intervals = monitor.close_session()
            if len(end_intervals) > last_logged_intervals_count:
                for i in range(last_logged_intervals_count, len(end_intervals)):
                    closed_int = end_intervals[i]
                    record_face_absence_interval(
                        session_id=session_id,
                        started_at=closed_int["started_at"],
                        ended_at=closed_int["ended_at"],
                        duration_seconds=closed_int["duration_seconds"],
                    )

            # Read back persisted intervals from database/examguard.db
            db_intervals = get_session_face_absence_intervals(session_id)
            total_duration = get_total_face_absence_duration(session_id)

            print("[SQLite Persistence Verification - database/examguard.db]")
            print(f"Total Recorded Intervals in DB: {len(db_intervals)}")
            for idx, interval in enumerate(db_intervals, 1):
                print(
                    f"  [{idx}] Started: {interval['started_at']} | "
                    f"Ended: {interval['ended_at']} | "
                    f"Duration: {interval['duration_seconds']} seconds"
                )
            print(f"Total Calculated Face Absence Duration: {total_duration} seconds")
            print("=" * 70)

        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds for live proctoring test")
    parser.add_argument("--camera", type=int, default=0, help="Webcam device index")
    args = parser.parse_args()
    run_live_webcam_proctor(duration_seconds=args.duration, camera_index=args.camera)
