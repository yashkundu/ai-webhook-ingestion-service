from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import DeadLetter, RawWebhook
from app.schemas.base import EventType, WebhookStatus
from app.schemas.registry import SchemaRegistry
from app.services import persistence
from app.services.llm import get_llm_provider
from app.services.llm.base import LLMProvider
from app.services.prompts import EXTRACTION_FAILED_MARKER

log = logging.getLogger(__name__)


async def _write_dlq(
    session: AsyncSession,
    raw: RawWebhook,
    error_type: str,
    message: str,
    context: dict[str, Any] | None = None,
) -> None:
    session.add(
        DeadLetter(
            id=str(uuid.uuid4()),
            raw_webhook_id=raw.id,
            error_type=error_type,
            error_message=message[:20000],
            context=context,
        )
    )
    raw.status = WebhookStatus.FAILED.value
    await session.flush()
    log.warning("webhook %s -> DLQ: %s %s", raw.id, error_type, message[:500])


async def process_webhook_id(session: AsyncSession, webhook_id: str) -> None:
    """Load raw webhook, classify, extract, validate, persist; or DLQ."""
    r = await session.execute(select(RawWebhook).where(RawWebhook.id == webhook_id))
    raw = r.scalar_one_or_none()
    if not raw:
        log.error("raw webhook not found: %s", webhook_id)
        return

    if raw.status in (WebhookStatus.COMPLETED.value,):
        return

    raw.status = WebhookStatus.PROCESSING.value
    await session.flush()

    llm: LLMProvider = get_llm_provider()
    try:
        payload: dict[str, Any] = json.loads(raw.body_json)
    except json.JSONDecodeError as e:
        await _write_dlq(session, raw, "JSONDecodeError", str(e), {"body": raw.body_json[:2000]})
        return

    try:
        event_type = await llm.classify(payload)
    except Exception as e:
        await _write_dlq(
            session, raw, "ClassificationError", repr(e), {"stage": "classify"}
        )
        return

    if event_type == EventType.UNCLASSIFIED:
        raw.status = WebhookStatus.COMPLETED.value
        await session.flush()
        return

    prev_err: str | None = None
    data: dict[str, Any] | None = None
    last_exc: Exception | None = None

    for attempt in range(settings.max_extraction_attempts):
        try:
            data = await llm.extract(
                event_type, payload, raw.vendor_id, previous_errors=prev_err
            )
            if isinstance(data, dict) and data.get(EXTRACTION_FAILED_MARKER) is True:
                await _write_dlq(
                    session,
                    raw,
                    "ExtractionInsufficientData",
                    str(data.get("reason", "missing or ambiguous fields"))[:20000],
                    {
                        "event_type": event_type,
                        "missing_fields": data.get("missing_fields"),
                        "model_response": data,
                    },
                )
                return
            # Authoritative source of truth for multi-tenant routing: URL path
            if isinstance(data, dict):
                data = {**data, "vendorId": raw.vendor_id}
            obj = SchemaRegistry.parse(event_type, data)
            await persistence.upsert_normalized(session, event_type, raw.id, obj)
            raw.status = WebhookStatus.COMPLETED.value
            await session.flush()
            return
        except ValidationError as e:
            prev_err = e.json()
            last_exc = e
            log.info(
                "validation attempt %s failed for %s: %s",
                attempt + 1,
                raw.id,
                prev_err[:1000],
            )
        except Exception as e:
            last_exc = e
            prev_err = repr(e)
            log.exception("extraction error %s: %s", raw.id, e)

    if last_exc is not None:
        await _write_dlq(
            session,
            raw,
            "ExhaustedRetries",
            str(last_exc)[:20000],
            {
                "event_type": event_type,
                "last_payload": (data or {}) if isinstance(data, dict) else None,
            },
        )
