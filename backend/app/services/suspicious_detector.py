"""Rule-based Suspicious Event Detector Service for Milestone 2."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .event_logger import (
    count_session_events,
    get_session_face_absence_intervals,
    get_total_face_absence_duration,
)


@dataclass
class SuspiciousThresholdConfig:
    max_tab_switches: int = 3
    max_face_absence_seconds: float = 120.0
    max_focus_loss_events: int = 3
    max_multiple_faces_events: int = 0


def detect_suspicious_events(
    session_id: int,
    config: Optional[SuspiciousThresholdConfig] = None,
) -> List[Dict[str, Any]]:
    """Evaluate actual session events against configurable thresholds and return detected suspicious events."""
    if config is None:
        config = SuspiciousThresholdConfig()

    suspicious_events: List[Dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Tab switches
    tab_switch_count = count_session_events(session_id, "tab_switch")
    if tab_switch_count > config.max_tab_switches:
        suspicious_events.append({
            "event_type": "TAB_SWITCH_THRESHOLD_EXCEEDED",
            "session_id": session_id,
            "observed": tab_switch_count,
            "threshold": config.max_tab_switches,
            "timestamp": now_iso,
            "details": f"Observed {tab_switch_count} tab switches exceeding threshold of {config.max_tab_switches}",
        })

    # 2. Face absence duration
    total_absence = get_total_face_absence_duration(session_id)
    if total_absence > config.max_face_absence_seconds:
        suspicious_events.append({
            "event_type": "FACE_ABSENCE_THRESHOLD_EXCEEDED",
            "session_id": session_id,
            "observed_duration": total_absence,
            "threshold": config.max_face_absence_seconds,
            "timestamp": now_iso,
            "details": f"Observed {total_absence} seconds face absence exceeding threshold of {config.max_face_absence_seconds} seconds",
        })

    # 3. Focus loss
    focus_loss_count = count_session_events(session_id, "focus_loss")
    if focus_loss_count > config.max_focus_loss_events:
        suspicious_events.append({
            "event_type": "FOCUS_LOSS_THRESHOLD_EXCEEDED",
            "session_id": session_id,
            "observed": focus_loss_count,
            "threshold": config.max_focus_loss_events,
            "timestamp": now_iso,
            "details": f"Observed {focus_loss_count} focus loss events exceeding threshold of {config.max_focus_loss_events}",
        })

    # 4. Multiple faces
    multiple_faces_count = count_session_events(session_id, "multiple_faces")
    if multiple_faces_count > config.max_multiple_faces_events:
        suspicious_events.append({
            "event_type": "MULTIPLE_FACES_DETECTED",
            "session_id": session_id,
            "observed": multiple_faces_count,
            "threshold": config.max_multiple_faces_events,
            "timestamp": now_iso,
            "details": f"Multiple faces detected {multiple_faces_count} times",
        })

    return suspicious_events


def get_monitoring_summary(
    session_id: int,
    config: Optional[SuspiciousThresholdConfig] = None,
) -> Dict[str, Any]:
    """Return an aggregated monitoring telemetry summary and detected suspicious events for a session."""
    if config is None:
        config = SuspiciousThresholdConfig()

    tab_switch_count = count_session_events(session_id, "tab_switch")
    focus_loss_count = count_session_events(session_id, "focus_loss")
    multiple_faces_count = count_session_events(session_id, "multiple_faces")
    total_absence_seconds = get_total_face_absence_duration(session_id)
    absence_intervals = get_session_face_absence_intervals(session_id)
    suspicious_events = detect_suspicious_events(session_id, config)

    return {
        "session_id": session_id,
        "tab_switches": tab_switch_count,
        "focus_loss_count": focus_loss_count,
        "multiple_faces_count": multiple_faces_count,
        "face_absence_seconds": total_absence_seconds,
        "absence_intervals": absence_intervals,
        "suspicious_events": suspicious_events,
        "thresholds": {
            "max_tab_switches": config.max_tab_switches,
            "max_face_absence_seconds": config.max_face_absence_seconds,
            "max_focus_loss_events": config.max_focus_loss_events,
            "max_multiple_faces_events": config.max_multiple_faces_events,
        },
    }

