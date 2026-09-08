"""Data model representing proctors and institutional administrators."""

from dataclasses import dataclass
from typing import Any, Dict, Optional
import sqlite3


@dataclass
class AdminUser:
    """Represents a proctor or administrator."""

    id: Optional[int]
    full_name: str
    email: str
    password_hash: str
    role: str  # 'PROCTOR' or 'ADMIN'
    is_active: bool = True
    created_at: Optional[str] = None

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert to dictionary, omitting password_hash by default."""
        data = {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "role": self.role,
            "is_active": bool(self.is_active),
            "created_at": self.created_at,
        }
        if include_sensitive:
            data["password_hash"] = self.password_hash
        return data

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "AdminUser":
        """Build an AdminUser instance from a SQLite row."""
        return cls(
            id=row["id"],
            full_name=row["full_name"],
            email=row["email"],
            password_hash=row["password_hash"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )
