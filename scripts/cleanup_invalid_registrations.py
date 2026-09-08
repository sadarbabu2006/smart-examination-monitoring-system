"""Script to safely audit and clean up target invalid test candidate registrations.

Creates a timestamped backup before deletion, operates in a database transaction,
removes only candidate-owned dependent records and files, and preserves all valid
candidates, admin/proctor records, and unrelated sessions.
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def get_table_counts(con):
    tables = [
        "candidates",
        "exam_sessions",
        "monitoring_events",
        "face_absence_intervals",
        "integrity_scores",
        "proctor_admins",
    ]
    counts = {}
    for t in tables:
        try:
            counts[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.OperationalError:
            counts[t] = 0
    return counts


def cleanup_target_candidate(db_path=None, target_email="dev@123.com"):
    if db_path is None:
        db_path = PROJECT_ROOT / "database" / "examguard.db"
    db_path = Path(db_path)

    if not db_path.exists():
        print(f"Database file not found at: {db_path}")
        return {"status": "error", "message": "Database not found"}

    # 1. Create a timestamped backup before destructive deletion
    from datetime import timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    backup_path = db_path.parent / f"examguard_backup_{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    print(f"[BACKUP] Created timestamped backup at: {backup_path}")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")

    before_counts = get_table_counts(con)
    print("\n--- BEFORE DELETION COUNTS ---")
    for tbl, cnt in before_counts.items():
        print(f"  {tbl}: {cnt}")

    # 2. Identify candidate by exact email
    candidate = con.execute(
        "SELECT * FROM candidates WHERE email = ?", (target_email,)
    ).fetchone()

    if not candidate:
        print(f"\n[INFO] Candidate with email '{target_email}' was not found. No records deleted.")
        con.close()
        return {
            "status": "not_found",
            "target_email": target_email,
            "backup_path": str(backup_path),
            "before_counts": before_counts,
            "after_counts": before_counts,
            "deleted": {},
        }

    cand_id = candidate["id"]
    print(f"\n[FOUND] Target candidate ID: {cand_id}")
    print(f"  Name: {candidate['full_name']}")
    print(f"  Email: {candidate['email']}")
    print(f"  Username: {candidate['username']}")
    print(f"  Created At: {candidate['created_at']}")
    print(f"  Photo Path: {candidate['registration_photo_path']}")

    # 3. Count dependent records
    sessions = con.execute(
        "SELECT id FROM exam_sessions WHERE candidate_id = ?", (cand_id,)
    ).fetchall()
    session_ids = [s["id"] for s in sessions]

    monitoring_count = 0
    absence_count = 0
    integrity_count = 0

    for sid in session_ids:
        monitoring_count += con.execute(
            "SELECT COUNT(*) FROM monitoring_events WHERE session_id = ?", (sid,)
        ).fetchone()[0]
        absence_count += con.execute(
            "SELECT COUNT(*) FROM face_absence_intervals WHERE session_id = ?", (sid,)
        ).fetchone()[0]
        integrity_count += con.execute(
            "SELECT COUNT(*) FROM integrity_scores WHERE session_id = ?", (sid,)
        ).fetchone()[0]

    print("\n--- DEPENDENT RECORDS TO REMOVE ---")
    print(f"  Exam Sessions: {len(session_ids)}")
    print(f"  Monitoring Events: {monitoring_count}")
    print(f"  Face Absence Intervals: {absence_count}")
    print(f"  Integrity Scores: {integrity_count}")

    photo_path_str = candidate["registration_photo_path"]
    photo_deleted = False

    # 4. Transactional deletion
    try:
        with con:
            for sid in session_ids:
                con.execute("DELETE FROM integrity_scores WHERE session_id = ?", (sid,))
                con.execute("DELETE FROM face_absence_intervals WHERE session_id = ?", (sid,))
                con.execute("DELETE FROM monitoring_events WHERE session_id = ?", (sid,))

            if session_ids:
                con.execute("DELETE FROM exam_sessions WHERE candidate_id = ?", (cand_id,))

            con.execute("DELETE FROM candidates WHERE id = ?", (cand_id,))

        # 5. Delete candidate-owned files only after DB commit succeeds
        if photo_path_str:
            try:
                p = Path(photo_path_str).resolve()
                if p.is_file():
                    p.unlink(missing_ok=True)
                    photo_deleted = True
                    print(f"[FILE] Deleted candidate registration photo: {photo_path_str}")
            except Exception as file_err:
                print(f"[WARNING] Could not delete photo file {photo_path_str}: {file_err}")

    except Exception as e:
        con.rollback()
        print(f"[ERROR] Transaction failed, rolled back: {e}")
        con.close()
        raise e

    after_counts = get_table_counts(con)
    print("\n--- AFTER DELETION COUNTS ---")
    for tbl, cnt in after_counts.items():
        print(f"  {tbl}: {cnt}")

    con.close()
    return {
        "status": "deleted",
        "candidate_id": cand_id,
        "target_email": target_email,
        "backup_path": str(backup_path),
        "sessions_deleted": len(session_ids),
        "monitoring_events_deleted": monitoring_count,
        "face_absence_deleted": absence_count,
        "integrity_records_deleted": integrity_count,
        "reports_deleted": 0,
        "evidence_files_deleted": 0,
        "photo_deleted": photo_deleted,
        "before_counts": before_counts,
        "after_counts": after_counts,
    }


def main():
    target_email = sys.argv[1] if len(sys.argv) > 1 else "dev@123.com"
    print(f"Starting cleanup for target candidate: {target_email}...")
    res = cleanup_target_candidate(target_email=target_email)
    print("\nCleanup summary:")
    for k, v in res.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
