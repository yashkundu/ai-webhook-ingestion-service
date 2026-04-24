from __future__ import annotations

import logging

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.base import EventType
from app.services.normalized_handlers import PERSIST_BY_EVENT

log = logging.getLogger(__name__)


async def upsert_normalized(
    session: AsyncSession,
    event_type: EventType,
    raw_webhook_id: str,
    model: BaseModel,
) -> None:
    """Insert normalized row once per raw webhook; no-op if row exists. Unknown types no-op."""
    handler = PERSIST_BY_EVENT.get(event_type)
    if handler is None:
        log.debug("no normalized record for %s", event_type)
        return
    await handler(session, raw_webhook_id, model)
