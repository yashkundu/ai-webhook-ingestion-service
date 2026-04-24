from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class ShipmentStatus(str, Enum):
    TRANSIT = "TRANSIT"
    DELIVERED = "DELIVERED"
    EXCEPTION = "EXCEPTION"


def _parse_iso8601(v: str) -> datetime:
    s = v.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


class ShipmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    vendorId: str
    trackingNumber: str
    status: ShipmentStatus
    timestamp: datetime

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_datetime(cls, v: datetime | str) -> datetime:
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return _parse_iso8601(v)
        raise TypeError("timestamp must be datetime or ISO 8601 string")
