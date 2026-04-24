from __future__ import annotations

import asyncio
import json
import random
from typing import Any

from app.config import settings
from app.schemas.base import EventType
from app.schemas.registry import SchemaRegistry


def _low_blob(payload: Any) -> str:
    return json.dumps(payload, default=str, ensure_ascii=False).lower()


class MockLLMProvider:
    """
    Simulates: latency, occasional HTTP-like failures, malformed JSON, and
    simple heuristic classification for predictable tests.
    """

    def __init__(self) -> None:
        self._rand = random.Random(42)
        if settings.mock_llm_error_rate or settings.mock_llm_malformed_rate:
            self._rand = random.Random()

    async def classify(self, payload: dict[str, Any]) -> EventType:
        await self._delay()
        self._maybe_fail()
        text = _low_blob(payload)
        if "force_invoice" in text:
            return EventType.INVOICE
        if "force_shipment" in text or "force_tracking" in text:
            return EventType.SHIPMENT_UPDATE
        if "force_unclassified" in text or "gibberish" in text:
            return EventType.UNCLASSIFIED
        g = SchemaRegistry.fuzzy_classified_match(text)
        if g is not None:
            return g
        return EventType.UNCLASSIFIED

    async def extract(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        vendor_id: str,
        previous_errors: str | None,
    ) -> dict[str, Any]:
        _ = previous_errors
        _ = payload
        await self._delay()
        self._maybe_malformed()
        self._maybe_fail()
        if event_type == EventType.UNCLASSIFIED:
            return {}
        entry = SchemaRegistry.get(event_type)
        if entry.mock_extract is not None:
            return entry.mock_extract(vendor_id)
        return {}

    async def _delay(self) -> None:
        ms = max(0, settings.mock_llm_latency_ms)
        await asyncio.sleep(ms / 1000.0)

    def _maybe_fail(self) -> None:
        if self._rand.random() < settings.mock_llm_error_rate:
            raise RuntimeError("mock LLM simulated failure")

    def _maybe_malformed(self) -> None:
        if self._rand.random() < settings.mock_llm_malformed_rate:
            raise ValueError("mock LLM returned malformed (simulated parse failure)")
