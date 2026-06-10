"""Celery configuration and application setup."""

import asyncio

from celery import Celery  # type: ignore[import-untyped]
from celery.signals import worker_process_init, worker_process_shutdown

from app.core.clients.database import engine
from app.core.clients.judge0 import init_judge0
from app.core.clients.redis import init_redis
from app.core.config import config
from app.core.logger import logger

celery_app = Celery(
    "amrita_icpc",
    broker=config.REDIS_URL,
    backend=config.REDIS_URL,
)

# Standard Celery configuration options
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)


@worker_process_init.connect
def init_worker_process(**kwargs):
    """Initialize async clients in the worker process."""

    # Dispose of the engine connection pool inherited from the parent process
    # so each worker creates its own pool bound to its own event loop.
    engine.sync_engine.dispose(close=False)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(init_redis())
        loop.run_until_complete(init_judge0())
    except Exception:
        logger.exception("Failed to initialize async clients in worker process")
        raise


@worker_process_shutdown.connect
def shutdown_worker_process(**kwargs):
    """Close async clients in the worker process."""
    import asyncio

    from app.core.clients.judge0 import close_judge0
    from app.core.clients.redis import close_redis

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(close_judge0())
        loop.run_until_complete(close_redis())
    except Exception:
        logger.exception("Failed to close async clients in worker process")
        raise
