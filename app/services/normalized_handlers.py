from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Invoice, Shipment, utcnow
from app.schemas.base import EventType
from app.schemas.invoice import InvoiceSchema
from app.schemas.shipment import ShipmentUpdate

log = logging.getLogger(__name__)

PersistFn = Callable[[AsyncSession, str, BaseModel], Awaitable[None]]


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


async def _upsert_shipment(
    session: AsyncSession, raw_webhook_id: str, model: BaseModel
) -> None:
    s = model if isinstance(model, ShipmentUpdate) else ShipmentUpdate.model_validate(model)
    ins = sqlite_insert(Shipment).values(
        id=str(uuid.uuid4()),
        raw_webhook_id=raw_webhook_id,
        vendor_id=s.vendorId,
        tracking_number=s.trackingNumber,
        status=s.status.value,
        timestamp=_aware(s.timestamp),
        created_at=utcnow(),
    )
    stmt = ins.on_conflict_do_nothing(index_elements=[Shipment.raw_webhook_id])
    await session.execute(stmt)


async def _upsert_invoice(
    session: AsyncSession, raw_webhook_id: str, model: BaseModel
) -> None:
    inv = model if isinstance(model, InvoiceSchema) else InvoiceSchema.model_validate(model)
    ins = sqlite_insert(Invoice).values(
        id=str(uuid.uuid4()),
        raw_webhook_id=raw_webhook_id,
        vendor_id=inv.vendorId,
        invoice_id=inv.invoiceId,
        amount=inv.amount,
        currency=inv.currency,
        created_at=utcnow(),
    )
    stmt = ins.on_conflict_do_nothing(index_elements=[Invoice.raw_webhook_id])
    await session.execute(stmt)


# Register alongside SchemaRegistry: one handler per event type with normalized storage.
PERSIST_BY_EVENT: dict[EventType, PersistFn] = {
    EventType.SHIPMENT_UPDATE: _upsert_shipment,
    EventType.INVOICE: _upsert_invoice,
}
