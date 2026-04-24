from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.schemas.base import EventType


@runtime_checkable
class LLMProvider(Protocol):
    """Abstraction over Groq (real) or mock implementations."""

    async def classify(self, payload: dict[str, Any]) -> EventType: ...

    async def extract(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        vendor_id: str,
        previous_errors: str | None,
    ) -> dict[str, Any]: ...
