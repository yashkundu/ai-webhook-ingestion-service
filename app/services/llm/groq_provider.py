from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings
from app.schemas.base import EventType
from app.schemas.registry import SchemaRegistry
from app.services import prompts
from app.services.llm.base import LLMProvider

log = logging.getLogger(__name__)

_DEBUG_SEP = "=" * 72


def _debug_pretty_json_if_object(s: str) -> str:
    try:
        obj = json.loads(s.strip())
        if isinstance(obj, (dict, list)):
            return json.dumps(obj, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        pass
    return s


def _parse_json_object(s: str) -> dict[str, Any]:
    t = s.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t[3:]
    if t.rstrip().endswith("```"):
        t = t.rsplit("```", 1)[0]
    t = t.strip()
    return json.loads(t)


class GroqProvider(LLMProvider):
    def __init__(self) -> None:
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        self._url = f"{settings.groq_base_url.rstrip('/')}/chat/completions"
        self._model = settings.groq_model
        self._headers = {
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        }

    def _body(self, system: str, user: str) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.3, min=0.3, max=4),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException, json.JSONDecodeError)),
    )
    async def _call(self, system: str, user: str) -> dict[str, Any]:
        body = self._body(system, user)
        if settings.debug:
            rf = json.dumps(body.get("response_format"), ensure_ascii=False)
            log.info(
                "%s\nGroq LLM request model=%r temperature=%s response_format=%s\n"
                "%s\n--- system ---\n%s\n%s\n--- user ---\n%s\n%s",
                _DEBUG_SEP,
                body["model"],
                body["temperature"],
                rf,
                _DEBUG_SEP,
                system,
                _DEBUG_SEP,
                user,
                _DEBUG_SEP,
            )
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(self._url, headers=self._headers, json=body)
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        if settings.debug:
            usage = data.get("usage")
            usage_s = json.dumps(usage, ensure_ascii=False, indent=2) if usage else "null"
            log.info(
                "%s\nGroq LLM response\n--- usage ---\n%s\n%s\n--- message.content ---\n%s\n%s",
                _DEBUG_SEP,
                usage_s,
                _DEBUG_SEP,
                _debug_pretty_json_if_object(content),
                _DEBUG_SEP,
            )
        return _parse_json_object(content)

    async def classify(self, payload: dict[str, Any]) -> EventType:
        raw = await self._call(
            prompts.classify_system_prompt(),
            prompts.classify_user_payload(payload),
        )
        t = (raw.get("type") or raw.get("event") or raw.get("classification") or "").upper()
        label_map = SchemaRegistry.label_to_classified_event()
        for k, v in label_map.items():
            if k in t or t == k:
                return v
        # fuzzy
        s = str(raw).lower()
        if "unclassified" in s or "other" in s:
            return EventType.UNCLASSIFIED
        guess = SchemaRegistry.fuzzy_classified_match(s)
        if guess is not None:
            return guess
        log.warning("classify: unexpected model output %s; defaulting UNCLASSIFIED", raw)
        return EventType.UNCLASSIFIED

    async def extract(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        vendor_id: str,
        previous_errors: str | None,
    ) -> dict[str, Any]:
        _ = SchemaRegistry.get(event_type)  # validate known type
        raw = await self._call(
            prompts.extract_system_prompt(),
            prompts.extract_user_message(
                event_type, payload, previous_errors=previous_errors
            ),
        )
        if not isinstance(raw, dict):
            raise ValueError("extraction result must be a JSON object")
        return raw
