"""Monitoring event and face absence interval models for Milestone 2."""

from dataclasses import dataclass
import json
from typing import Any, Optional


@dataclass
class MonitoringEvent:
    id: Optional[int]
    session_id: int
    event_type: str
    timestamp: str
    details: Optional[Any] = None

    def to_dict(self) -> dict:
        parsed_details = self.details
        if isinstance(self.details, str):
            try:
                parsed_details = json.loads(self.details)
            except Exception:
                parsed_details = self.details
        return {
            "id": self.id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "details": parsed_details,
        }

    @classmethod
    def from_row(cls, row) -> Optional["MonitoringEvent"]:
        if row is None:
            return None
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            event_type=row["event_type"],
            timestamp=row["timestamp"],
            details=row["details"] if "details" in row.keys() else None,
        )


@dataclass
class FaceAbsenceInterval:
    id: Optional[int]
    session_id: int
    started_at: str
    ended_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    created_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row) -> Optional["FaceAbsenceInterval"]:
        if row is None:
            return None
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"] if "ended_at" in row.keys() else None,
            duration_seconds=row["duration_seconds"] if "duration_seconds" in row.keys() else None,
            created_at=row["created_at"] if "created_at" in row.keys() else None,
        )

