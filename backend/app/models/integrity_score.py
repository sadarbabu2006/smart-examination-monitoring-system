"""Integrity Score Model.

Maintains computed trust index and credibility metrics per candidate session,
aggregating penalty points deducted across suspicious event occurrences.
"""

from dataclasses import dataclass
import json
from typing import Any, Dict, Optional


@dataclass
class IntegrityScore:
    id: Optional[int]
    session_id: int
    integrity_score: int
    risk_level: str
    face_presence_ratio: Optional[float]
    monitored_duration_seconds: Optional[float]
    face_absence_seconds: Optional[float]
    suspicious_event_count: int
    breakdown: Dict[str, Any]
    calculated_at: str

    def to_dict(self) -> Dict[str, Any]:
        parsed_breakdown = self.breakdown
        if isinstance(self.breakdown, str):
            try:
                parsed_breakdown = json.loads(self.breakdown)
            except Exception:
                parsed_breakdown = self.breakdown

        return {
            "id": self.id,
            "session_id": self.session_id,
            "integrity_score": self.integrity_score,
            "risk_level": self.risk_level,
            "face_presence_ratio": self.face_presence_ratio,
            "monitored_duration_seconds": self.monitored_duration_seconds,
            "face_absence_seconds": self.face_absence_seconds,
            "suspicious_event_count": self.suspicious_event_count,
            "breakdown": parsed_breakdown,
            "calculated_at": self.calculated_at,
        }

    @classmethod
    def from_row(cls, row) -> Optional["IntegrityScore"]:
        if row is None:
            return None

        breakdown_val = row["breakdown"]
        if isinstance(breakdown_val, str):
            try:
                breakdown_val = json.loads(breakdown_val)
            except Exception:
                pass

        return cls(
            id=row["id"],
            session_id=row["session_id"],
            integrity_score=row["integrity_score"],
            risk_level=row["risk_level"],
            face_presence_ratio=row["face_presence_ratio"],
            monitored_duration_seconds=row["monitored_duration_seconds"],
            face_absence_seconds=row["face_absence_seconds"],
            suspicious_event_count=row["suspicious_event_count"],
            breakdown=breakdown_val,
            calculated_at=row["calculated_at"],
        )
