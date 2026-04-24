from __future__ import annotations

import asyncio
import uuid
from typing import Optional

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy import select

from app.db import async_session_factory, init_db
from app.models import RawWebhook, Shipment


@pytest.mark.asyncio
async def test_ingest_returns_202() -> None:
    from app.main import app

    vid = f"co-{uuid.uuid4()}"
    async with LifespanManager(app, startup_timeout=30.0, shutdown_timeout=30.0):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30.0
        ) as client:
            r = await client.post(
                f"/webhooks/{vid}",
                json={"message": "tracking force_shipment something"},
            )
            assert r.status_code == 202
            data = r.json()
    assert "webhook_id" in data
    assert data["queued"] in (True, False)


@pytest.mark.asyncio
async def test_end_to_end_shipment_persisted() -> None:
    from app.main import app

    await init_db()
    vid = f"ship-{uuid.uuid4()}"
    last_status: Optional[str] = None
    async with LifespanManager(app, startup_timeout=30.0, shutdown_timeout=30.0):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30.0
        ) as client:
            r = await client.post(
                f"/webhooks/{vid}",
                json={"type": "force_shipment", "meta": "tracking"},
            )
            assert r.status_code == 202
            wid = r.json()["webhook_id"]
        # Lifespan (and workers) must stay up while we poll
        await asyncio.sleep(0.3)
        for _ in range(200):
            async with async_session_factory() as s:
                w = (
                    await s.execute(
                        select(RawWebhook).where(RawWebhook.id == wid)  # noqa: E501
                    )
                ).scalar_one_or_none()
                if w:
                    last_status = w.status
                if w and w.status == "COMPLETED":
                    r2 = await s.execute(
                        select(Shipment).where(Shipment.raw_webhook_id == wid)
                    )
                    row = r2.scalar_one_or_none()
                    if row:
                        assert row.vendor_id == vid
                        assert row.tracking_number
                        return
            await asyncio.sleep(0.1)
    assert False, f"shipment not processed, last status={last_status!r}"
