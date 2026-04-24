"""
Env must be set before app/config/db are first imported.
"""
import os
from pathlib import Path

_db = Path(__file__).parent / "test_state.sqlite"
if _db.exists():
    _db.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_db}"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["MOCK_LLM_ERROR_RATE"] = "0.0"
os.environ["MOCK_LLM_MALFORMED_RATE"] = "0.0"
os.environ["QUEUE_MAX_SIZE"] = "10000"
