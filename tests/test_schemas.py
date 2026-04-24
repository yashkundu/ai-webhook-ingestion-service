import pytest
from pydantic import ValidationError

from app.schemas.invoice import InvoiceSchema
from app.schemas.shipment import ShipmentStatus, ShipmentUpdate


def test_shipment_update_valid() -> None:
    s = ShipmentUpdate.model_validate(
        {
            "vendorId": "v1",
            "trackingNumber": "T1",
            "status": "TRANSIT",
            "timestamp": "2025-01-15T10:00:00Z",
        }
    )
    assert s.status == ShipmentStatus.TRANSIT
    assert s.timestamp.tzinfo is not None


def test_shipment_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        ShipmentUpdate.model_validate(
            {
                "vendorId": "v1",
                "trackingNumber": "T1",
                "status": "DELIVERED",
                "timestamp": "2025-01-15T10:00:00Z",
                "foo": 1,
            }
        )


def test_invoice_valid() -> None:
    i = InvoiceSchema.model_validate(
        {
            "vendorId": "v1",
            "invoiceId": "INV-1",
            "amount": 10.5,
            "currency": "usd",  # normalized to upper
        }
    )
    assert i.currency == "USD"


def test_invoice_bad_currency() -> None:
    with pytest.raises(ValidationError):
        InvoiceSchema.model_validate(
            {
                "vendorId": "v1",
                "invoiceId": "I",
                "amount": 1.0,
                "currency": "USDD",
            }
        )
