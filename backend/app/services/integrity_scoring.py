"""Integrity Scoring Engine for ExamGuard.

Calculates a normalized, deterministic, and explainable Integrity Score (0-100)
for completed exam sessions based on verified telemetry violations, face presence
ratios, and duration of suspicious activities.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional

from ..database.db import get_db
from ..models.integrity_score import IntegrityScore
from .event_logger import (
    get_session_events,
    get_session_face_absence_intervals,
    get_total_face_absence_duration,
)

logger = logging.getLogger(__name__)


@dataclass
class IntegrityScoringConfig:
    """Configurable scoring parameters, weights, and thresholds."""
    base_score: int = 100

    # Violation point penalties
    penalty_focus_loss: int = 3
    penalty_visibility_change: int = 3
    penalty_window_blur: int = 4
    penalty_tab_switch: int = 5
    penalty_multiple_faces: int = 15

    # Duration-based face absence penalties (points per 30 seconds of absence)
    penalty_absence_per_30s: float = 5.0
    max_absence_penalty: int = 40

    # Risk level thresholds
    low_risk_threshold: int = 80    # 80 - 100: LOW RISK
    medium_risk_threshold: int = 50 # 50 - 79:  MEDIUM RISK (0 - 49: HIGH RISK)


def _parse_timestamp(ts: Optional[Any]) -> Optional[datetime]:
    """Safely parse an ISO format timestamp string or datetime into UTC datetime."""
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def calculate_session_duration(session_row: Dict[str, Any], events: List[Dict[str, Any]]) -> float:
    """Calculate total monitored session duration in seconds.
    
    Uses session start/end timestamps when available; falls back to event timestamps.
    Returns 0.0 if duration cannot be reliably determined.
    """
    start_dt = _parse_timestamp(session_row.get("started_at"))
    end_dt = _parse_timestamp(session_row.get("ended_at"))

    if start_dt and end_dt:
        diff = (end_dt - start_dt).total_seconds()
        return max(0.0, round(diff, 2))

    # Fallback to earliest and latest event timestamps if available
    timestamps = []
    if start_dt:
        timestamps.append(start_dt)
    if end_dt:
        timestamps.append(end_dt)

    for ev in events:
        ts = _parse_timestamp(ev.get("timestamp"))
        if ts:
            timestamps.append(ts)

    if len(timestamps) >= 2:
        timestamps.sort()
        diff = (timestamps[-1] - timestamps[0]).total_seconds()
        return max(0.0, round(diff, 2))

    return 0.0


def calculate_face_presence_ratio(total_absence_seconds: float, monitored_duration_seconds: float) -> Optional[float]:
    """Calculate face presence ratio between 0.0 and 1.0.
    
    Returns None if monitored duration is missing or zero (to avoid division by zero).
    """
    if monitored_duration_seconds <= 0.0:
        return None

    face_present_seconds = max(0.0, monitored_duration_seconds - total_absence_seconds)
    ratio = face_present_seconds / monitored_duration_seconds
    return round(min(1.0, max(0.0, ratio)), 4)


def calculate_session_integrity(
    session_id: int,
    config: Optional[IntegrityScoringConfig] = None,
) -> Dict[str, Any]:
    """Compute the deterministic integrity evaluation for an examination session."""
    if config is None:
        config = IntegrityScoringConfig()

    db = get_db()
    session_row = db.execute("SELECT * FROM exam_sessions WHERE id = ?", (session_id,)).fetchone()
    if not session_row:
        raise ValueError(f"Exam session {session_id} does not exist.")

    session_dict = dict(session_row)
    events = get_session_events(session_id)
    total_absence_seconds = get_total_face_absence_duration(session_id)
    duration_seconds = calculate_session_duration(session_dict, events)
    face_ratio = calculate_face_presence_ratio(total_absence_seconds, duration_seconds)

    # 1. Group events and count violations
    event_counts: Dict[str, int] = {
        "tab_switch": 0,
        "focus_loss": 0,
        "window_blur": 0,
        "visibility_change": 0,
        "multiple_faces": 0,
        "other_suspicious": 0,
    }

    for ev in events:
        raw_type = (ev.get("event_type") or "").strip().lower()
        if raw_type in ("tab_switch", "tab_switch_threshold_exceeded"):
            event_counts["tab_switch"] += 1
        elif raw_type in ("focus_loss", "focus_loss_threshold_exceeded"):
            event_counts["focus_loss"] += 1
        elif raw_type in ("window_blur", "blur"):
            event_counts["window_blur"] += 1
        elif raw_type in ("visibility_change", "visibilitychange"):
            event_counts["visibility_change"] += 1
        elif raw_type in ("multiple_faces", "multiple_faces_detected"):
            event_counts["multiple_faces"] += 1
        elif "suspicious" in raw_type or "violation" in raw_type:
            event_counts["other_suspicious"] += 1

    # 2. Calculate deductions
    deductions: Dict[str, int] = {}

    deductions["tab_switch"] = event_counts["tab_switch"] * config.penalty_tab_switch
    deductions["focus_loss"] = event_counts["focus_loss"] * config.penalty_focus_loss
    deductions["window_blur"] = event_counts["window_blur"] * config.penalty_window_blur
    deductions["visibility_change"] = event_counts["visibility_change"] * config.penalty_visibility_change
    deductions["multiple_faces"] = event_counts["multiple_faces"] * config.penalty_multiple_faces

    # Duration-based face absence deduction
    if total_absence_seconds > 0:
        absence_pts = (total_absence_seconds / 30.0) * config.penalty_absence_per_30s
        deductions["face_absence"] = int(min(config.max_absence_penalty, round(absence_pts)))
    else:
        deductions["face_absence"] = 0

    if event_counts["other_suspicious"] > 0:
        deductions["other_suspicious"] = event_counts["other_suspicious"] * 5

    total_deductions = sum(deductions.values())
    raw_score = config.base_score - total_deductions
    final_score = max(0, min(100, int(round(raw_score))))

    # 3. Determine Risk Level
    if final_score >= config.low_risk_threshold:
        risk_level = "LOW"
    elif final_score >= config.medium_risk_threshold:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    # Total suspicious event count
    suspicious_count = (
        event_counts["tab_switch"]
        + event_counts["focus_loss"]
        + event_counts["window_blur"]
        + event_counts["visibility_change"]
        + event_counts["multiple_faces"]
        + event_counts["other_suspicious"]
        + (1 if total_absence_seconds >= 30.0 else 0)
    )

    now_iso = datetime.now(timezone.utc).isoformat()

    # 4. Explainable breakdown
    explanation_parts = [f"Base score: {config.base_score}"]
    for category, pts in deductions.items():
        if pts > 0:
            explanation_parts.append(f"{category.replace('_', ' ').title()}: -{pts}")
    explanation_parts.append(f"Final score: {final_score} ({risk_level} RISK)")

    breakdown = {
        "base_score": config.base_score,
        "deductions": deductions,
        "total_deductions": total_deductions,
        "final_score": final_score,
        "risk_level": risk_level,
        "event_counts": event_counts,
        "monitored_duration_seconds": duration_seconds if duration_seconds > 0 else None,
        "face_absence_seconds": round(total_absence_seconds, 2),
        "face_presence_ratio": face_ratio,
        "summary_explanation": ". ".join(explanation_parts),
    }

    return {
        "session_id": session_id,
        "integrity_score": final_score,
        "risk_level": risk_level,
        "face_presence_ratio": face_ratio,
        "monitored_duration_seconds": duration_seconds if duration_seconds > 0 else None,
        "face_absence_seconds": round(total_absence_seconds, 2),
        "suspicious_event_count": suspicious_count,
        "breakdown": breakdown,
        "calculated_at": now_iso,
    }


def save_integrity_score(session_id: int, score_data: Dict[str, Any]) -> Dict[str, Any]:
    """Persist an integrity score result into the database idempotently."""
    db = get_db()
    breakdown_json = json.dumps(score_data.get("breakdown", {}))

    db.execute(
        """INSERT INTO integrity_scores (
            session_id, integrity_score, risk_level, face_presence_ratio,
            monitored_duration_seconds, face_absence_seconds, suspicious_event_count,
            breakdown, calculated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            integrity_score = excluded.integrity_score,
            risk_level = excluded.risk_level,
            face_presence_ratio = excluded.face_presence_ratio,
            monitored_duration_seconds = excluded.monitored_duration_seconds,
            face_absence_seconds = excluded.face_absence_seconds,
            suspicious_event_count = excluded.suspicious_event_count,
            breakdown = excluded.breakdown,
            calculated_at = excluded.calculated_at
        """,
        (
            session_id,
            score_data["integrity_score"],
            score_data["risk_level"],
            score_data.get("face_presence_ratio"),
            score_data.get("monitored_duration_seconds"),
            score_data.get("face_absence_seconds"),
            score_data.get("suspicious_event_count", 0),
            breakdown_json,
            score_data.get("calculated_at") or datetime.now(timezone.utc).isoformat(),
        ),
    )
    db.commit()

    saved = get_integrity_score(session_id)
    if not saved:
        raise RuntimeError(f"Failed to persist integrity score for session {session_id}")
    return saved


def get_integrity_score(session_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve the stored integrity score record for a session."""
    db = get_db()
    row = db.execute("SELECT * FROM integrity_scores WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        return None
    model = IntegrityScore.from_row(row)
    return model.to_dict() if model else None


def evaluate_and_persist_session_integrity(session_id: int) -> Optional[Dict[str, Any]]:
    """Helper to safely calculate and persist integrity score for a completed session.
    
    If scoring fails for any reason, logs error and returns None without raising an exception,
    ensuring that the underlying session submission remains uncorrupted.
    """
    try:
        result = calculate_session_integrity(session_id)
        saved = save_integrity_score(session_id, result)
        logger.info("Successfully recorded integrity score for session %s: %s (%s)",
                    session_id, saved["integrity_score"], saved["risk_level"])
        return saved
    except Exception as err:
        logger.error("Failed to calculate or persist integrity score for session %s: %s",
                     session_id, str(err), exc_info=True)
        return None
