import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_factory, init_db
from app.models import RawWebhook, Shipment
from app.schemas.base import WebhookStatus
from app.services.classifier import process_webhook_id


async def _add_raw(
    session: AsyncSession, vendor: str, body: dict, status: str = "PENDING"
) -> str:
    from app.utils import idempotency_key

    key = idempotency_key(vendor, body)
    w = RawWebhook(
        vendor_id=vendor,
        body_json=json.dumps(body),
        idempotency_key=key,
        status=status,
        queued=False,
    )
    session.add(w)
    await session.commit()
    await session.refresh(w)
    return w.id


@pytest.mark.asyncio
async def test_unclassified_marks_complete() -> None:
    await init_db()
    async with async_session_factory() as s:
        wid = await _add_raw(
            s,
            "v1",
            {"force_unclassified": True, "x": 1},
        )
    async with async_session_factory() as s:
        await process_webhook_id(s, wid)
        await s.commit()
    async with async_session_factory() as s:
        w = (await s.execute(select(RawWebhook).where(RawWebhook.id == wid))).scalar_one()  # noqa: E501
        assert w.status == WebhookStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_shipment_saves() -> None:
    await init_db()
    async with async_session_factory() as s:
        wid = await _add_raw(
            s,
            "acme",
            {"type": "force_shipment", "n": 1},
        )
    async with async_session_factory() as s:
        await process_webhook_id(s, wid)
        await s.commit()
    async with async_session_factory() as s:
        w = (await s.execute(select(RawWebhook).where(RawWebhook.id == wid))).scalar_one()  # noqa: E501
        assert w.status == WebhookStatus.COMPLETED.value
        sh = (
            await s.execute(select(Shipment).where(Shipment.raw_webhook_id == wid))
        ).scalar_one()
        assert sh.vendor_id == "acme"
