from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from repo root so DEBUG and other vars load even when cwd is not the project directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # e.g. DATABASE_URL, GROQ_API_KEY
        case_sensitive=False,
    )

    app_name: str = "ai-webhook-ingestion-service"
    # When true, enables verbose diagnostics (e.g. Groq request/response logging). Avoid in production with sensitive payloads.
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///./data/webhook.db"
    # Bounded queue for in-process backpressure
    queue_max_size: int = 1000
    worker_count: int = 4
    # LLM
    llm_provider: Literal["groq", "mock"] = "groq"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # Mock LLM
    mock_llm_latency_ms: int = 50
    mock_llm_error_rate: float = 0.0
    mock_llm_malformed_rate: float = 0.0
    # Extraction self-heal retries
    max_extraction_attempts: int = 2


settings = Settings()
