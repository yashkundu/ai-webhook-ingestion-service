from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    SHIPMENT_UPDATE = "SHIPMENT_UPDATE"
    INVOICE = "INVOICE"
    UNCLASSIFIED = "UNCLASSIFIED"


class WebhookStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
