import uuid

import httpx
import pytest
from asgi_lifespan import LifespanManager


@pytest.mark.asyncio
async def test_same_body_dedupes() -> None:
    from app.main import app

    vid = f"v{uuid.uuid4()}"
    body: dict = {"type": "force_shipment", "key": str(uuid.uuid4())}
    async with LifespanManager(app, startup_timeout=30.0, shutdown_timeout=30.0):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30.0
        ) as client:
            r1 = await client.post(f"/webhooks/{vid}", json=body)
            r2 = await client.post(f"/webhooks/{vid}", json=body)
    assert r1.status_code == 202
    assert r2.status_code == 202
    j1, j2 = r1.json(), r2.json()
    assert j1["webhook_id"] == j2["webhook_id"]
    assert j1["duplicate"] is False
    assert j2["duplicate"] is True
