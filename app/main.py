from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app import __version__
from app.api.health import router as health_router
from app.api.webhooks import router as webhooks_router
from app.config import settings
from app.services.queue import recover_pending, start_workers, stop_workers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await start_workers()
    n = await recover_pending()
    if n:
        log.info("startup: recovered %s pending webhooks to queue", n)
    yield
    await stop_workers()
    log.info("shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(webhooks_router, prefix="")
    return app


app = create_app()
