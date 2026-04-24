from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services import ingestion

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/{vendor_id}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest arbitrary JSON webhook (async processing)",
)
async def ingest(
    vendor_id: str,
    payload: Any = Body(..., description="Any JSON the vendor might send"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await ingestion.accept_webhook(session, vendor_id, payload)
    return {
        "webhook_id": result.webhook_id,
        "duplicate": result.duplicate,
        "queued": result.queued,
    }
