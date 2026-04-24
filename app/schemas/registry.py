from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Type

from pydantic import BaseModel

from app.schemas.base import EventType
from app.schemas.invoice import InvoiceSchema
from app.schemas.shipment import ShipmentUpdate


@dataclass(frozen=True)
class SchemaEntry:
    """Maps an event type to a strict Pydantic model and a prompt fragment for extraction."""

    event_type: EventType
    pydantic_model: Type[BaseModel]
    extract_instruction: str
    # Short line for the classify system prompt (what this label means).
    classify_blurb: str
    # Substrings (lowercased) for Groq fuzzy fallback when the model returns an unexpected shape.
    classification_keywords: frozenset[str] = frozenset()
    # Optional fake extraction for MockLLMProvider.
    mock_extract: Callable[[str], dict[str, Any]] | None = None


def _shipment_extraction() -> str:
    return (
        "Extract a shipment update. Fields: vendorId (string), "
        "trackingNumber (string), status (exactly one of: TRANSIT, DELIVERED, EXCEPTION; infer "
        "from vendor status text when one bucket clearly fits — hints here are illustrative only), "
        "timestamp as ISO 8601 (normalize from the payload when the instant is unambiguous)."
    )


def _invoice_extraction() -> str:
    return (
        "Extract an invoice. Fields: vendorId (string), invoiceId (string), "
        "amount (number, float), currency (3-letter ISO 4217 code)."
    )


def _mock_invoice_extract(vendor_id: str) -> dict[str, Any]:
    return {
        "vendorId": vendor_id,
        "invoiceId": "INV-MOCK-001",
        "amount": 19.99,
        "currency": "USD",
    }


def _mock_shipment_extract(vendor_id: str) -> dict[str, Any]:
    return {
        "vendorId": vendor_id,
        "trackingNumber": "1Z999AA10123456784",
        "status": "TRANSIT",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# Single registry: new event types = add one entry here.
_SCHEMAS: dict[EventType, SchemaEntry] = {
    EventType.SHIPMENT_UPDATE: SchemaEntry(
        event_type=EventType.SHIPMENT_UPDATE,
        pydantic_model=ShipmentUpdate,
        extract_instruction=_shipment_extraction(),
        classify_blurb=(
            "the message is primarily about a parcel/tracking/shipment status change"
        ),
        classification_keywords=frozenset(
            {
                "shipment",
                "ship",
                "track",
                "parcel",
                "carrier",
            }
        ),
        mock_extract=_mock_shipment_extract,
    ),
    EventType.INVOICE: SchemaEntry(
        event_type=EventType.INVOICE,
        pydantic_model=InvoiceSchema,
        extract_instruction=_invoice_extraction(),
        classify_blurb="the message is about billing, invoice, payment, amount, bill",
        classification_keywords=frozenset(
            {"invoice", "payment", "billing", "bill"}
        ),
        mock_extract=_mock_invoice_extract,
    ),
}


class SchemaRegistry:
    @staticmethod
    def get(event_type: EventType) -> SchemaEntry:
        if event_type not in _SCHEMAS:
            raise KeyError(f"Unknown classified event type: {event_type}")
        return _SCHEMAS[event_type]

    @staticmethod
    def model_json_schema(event_type: EventType) -> dict[str, Any]:
        return SchemaRegistry.get(event_type).pydantic_model.model_json_schema()

    @staticmethod
    def parse(event_type: EventType, data: dict[str, Any]) -> BaseModel:
        model = SchemaRegistry.get(event_type).pydantic_model
        return model.model_validate(data)

    @staticmethod
    def register(entry: SchemaEntry) -> None:
        """For tests and future extensibility: register a new schema at runtime."""
        _SCHEMAS[entry.event_type] = entry

    @staticmethod
    def all_keys() -> frozenset[EventType]:
        return frozenset(_SCHEMAS.keys())

    @staticmethod
    def label_to_classified_event() -> dict[str, EventType]:
        """Map JSON `type` string (enum value) to EventType, including UNCLASSIFIED."""
        m: dict[str, EventType] = {et.value: et for et in _SCHEMAS}
        m[EventType.UNCLASSIFIED.value] = EventType.UNCLASSIFIED
        return m

    @staticmethod
    def fuzzy_classified_match(s_lower: str) -> EventType | None:
        """
        If s_lower contains a registered keyword for exactly one type (first wins in enum order),
        return that type. Does not return UNCLASSIFIED.
        """
        for et in sorted(_SCHEMAS.keys(), key=lambda e: e.value):
            for kw in _SCHEMAS[et].classification_keywords:
                if kw in s_lower:
                    return et
        return None
