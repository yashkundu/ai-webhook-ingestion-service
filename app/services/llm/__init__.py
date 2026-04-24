from __future__ import annotations

from app.config import settings
from app.services.llm.base import LLMProvider
from app.services.llm.groq_provider import GroqProvider
from app.services.llm.mock_provider import MockLLMProvider


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "groq":
        return GroqProvider()  # type: ignore[return-value]
    return MockLLMProvider()  # type: ignore[return-value]
