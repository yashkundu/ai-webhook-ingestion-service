from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models import RawWebhook
from app.schemas.base import WebhookStatus
from app.services import queue
from app.utils import idempotency_key

log = logging.getLogger(__name__)


class IngestResult:
    def __init__(self, webhook_id: str, *, duplicate: bool, queued: bool) -> None:
        self.webhook_id = webhook_id
        self.duplicate = duplicate
        self.queued = queued


async def accept_webhook(
    session: AsyncSession,
    vendor_id: str,
    body: Any,
) -> IngestResult:
    """
    Persist raw body and enqueue for processing. De-dupe via idempotency key.
    Commits the new row *before* enqueueing so background workers can see it.
    """
    key = idempotency_key(vendor_id, body)
    r = await session.execute(select(RawWebhook).where(RawWebhook.idempotency_key == key))
    existing = r.scalar_one_or_none()
    if existing:
        await session.commit()
        return IngestResult(existing.id, duplicate=True, queued=True)

    body_str = json.dumps(body, default=str, ensure_ascii=False)
    raw = RawWebhook(
        vendor_id=vendor_id,
        body_json=body_str,
        idempotency_key=key,
        status=WebhookStatus.PENDING.value,
        queued=True,
    )
    session.add(raw)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        r2 = await session.execute(
            select(RawWebhook).where(RawWebhook.idempotency_key == key)
        )
        again = r2.scalar_one()
        await session.commit()
        return IngestResult(again.id, duplicate=True, queued=True)

    # Row visible to workers before any consumer can dequeue
    await session.commit()

    enq = await queue.submit_webhook_id(raw.id)
    if not enq:
        row = await session.get(RawWebhook, raw.id)
        if row:
            row.queued = False
            await session.commit()
        log.warning("queue full, webhook %s left PENDING; recovery on restart", raw.id)
    return IngestResult(raw.id, duplicate=False, queued=enq)
