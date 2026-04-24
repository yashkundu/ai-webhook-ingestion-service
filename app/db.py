from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    """Create parent directory for file-based SQLite; SQLite does not mkdir parents."""
    try:
        parsed = make_url(database_url)
    except Exception:
        return
    if not parsed.drivername.startswith("sqlite"):
        return
    db_path = parsed.database
    if not db_path or db_path == ":memory:":
        return
    Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

# SQLite needs check_same_thread for sync path; async uses aiosqlite
connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args=connect_args,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autobegin=True,
)


async def init_db() -> None:
    """Create all tables (dev-friendly; production uses Alembic)."""
    _ensure_sqlite_parent_dir(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields a session. Routes that mutate must commit/rollback themselves.
    (Needed so ingestion can commit before enqueuing work to the worker pool.)
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
