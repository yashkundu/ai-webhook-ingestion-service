from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Optional

from sqlalchemy import select

from app.config import settings
from app.db import async_session_factory, init_db
from app.models import RawWebhook
from app.schemas.base import WebhookStatus
from app.services.classifier import process_webhook_id

log = logging.getLogger(__name__)

# In-process task queue: created in start_workers() on the *running* event loop
# (a queue built at import time can bind the wrong loop and block workers).
_task_queue: Optional[asyncio.Queue[str]] = None
_worker_tasks: list[asyncio.Task[None]] = []


def _queue() -> asyncio.Queue[str]:
    if _task_queue is None:
        raise RuntimeError("Queue not started; start_workers() must run first")
    return _task_queue


async def submit_webhook_id(webhook_id: str) -> bool:
    """
    Enqueue a webhook for async processing. Returns True if enqueued, False if queue is full.
    """
    with suppress(asyncio.QueueFull):
        _queue().put_nowait(webhook_id)
        return True
    return False


async def recover_pending() -> int:
    """On startup, enqueue all raw webhooks that are still PENDING."""
    count = 0
    async with async_session_factory() as session:
        r = await session.execute(
            select(RawWebhook.id).where(
                RawWebhook.status == WebhookStatus.PENDING.value
            )
        )
        ids = [x[0] for x in r.all()]
    for wid in ids:
        ok = await submit_webhook_id(wid)
        if not ok:
            log.warning("recovery: queue full, remaining PENDING will catch on next restart")
            break
        count += 1
    log.info("recover_pending: re-enqueued %s webhooks", count)
    return count


async def _worker_main(worker_id: int) -> None:
    q = _queue()
    while True:
        webhook_id = await q.get()
        try:
            async with async_session_factory() as session:
                # Single transaction for process_webhook_id (commits on context exit)
                try:
                    await process_webhook_id(session, webhook_id)
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
        except Exception as e:
            log.exception("worker %s failed processing %s: %s", worker_id, webhook_id, e)
            # Best-effort: mark failed in new session
            try:
                async with async_session_factory() as s2:
                    r = await s2.get(RawWebhook, webhook_id)
                    if r and r.status == WebhookStatus.PROCESSING.value:
                        r.status = WebhookStatus.FAILED.value
                    await s2.commit()
            except Exception:
                log.exception("failed to mark webhook failed after worker error")
        finally:
            q.task_done()


async def start_workers() -> None:
    global _task_queue, _worker_tasks
    _task_queue = asyncio.Queue(maxsize=settings.queue_max_size)
    await init_db()
    n = max(1, settings.worker_count)
    _worker_tasks = []
    for i in range(n):
        t = asyncio.create_task(_worker_main(i + 1), name=f"webhook-worker-{i+1}")
        _worker_tasks.append(t)
    log.info("started %s queue workers, queue size max=%s", n, settings.queue_max_size)


async def stop_workers() -> None:
    global _task_queue
    for t in _worker_tasks:
        t.cancel()
    if _worker_tasks:
        await asyncio.gather(*_worker_tasks, return_exceptions=True)
    _worker_tasks.clear()
    _task_queue = None
