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
    # Explicitly register task modules so workers and Beat discover every stage.
    include=["worker.evaluation", "worker.poller"],
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
    # Backstop against a hung coroutine (stuck DB/Redis/HTTP call) permanently
    # occupying a worker slot: the soft limit raises SoftTimeLimitExceeded
    # inside the task so it can clean up (release gates, record a terminal
    # verdict); the hard limit kills the process if it still hasn't returned.
    task_soft_time_limit=150,
    task_time_limit=180,
    # Default queue for anything not explicitly routed below.
    task_default_queue="student_submit",
    # Dedicated queues isolate live student submissions from bulk re-evaluation
    # and from the (light) poller/persist work, so bulk jobs never starve the
    # interactive path.
    task_routes={
        "worker.evaluation.evaluate_submission": {"queue": "student_submit"},
        "worker.evaluation.evaluate_contest_submission": {
            "queue": "bulk_contest_evaluation"
        },
        "worker.evaluation.persist_evaluation": {"queue": "persist"},
        "worker.poller.poll_pending_evaluations": {"queue": "poller"},
    },
    # Coarse Judge0 guard layered on top of the Redis in-flight gate.
    task_annotations={
        "worker.evaluation.submit_evaluation": {"rate_limit": "30/s"},
    },
    # Run the central result poller on its own cadence.
    beat_schedule={
        "poll-pending-evaluations": {
            "task": "worker.poller.poll_pending_evaluations",
            "schedule": config.EVAL_POLL_INTERVAL_SECONDS,
            # `expires` must give the worker real headroom to fall behind under
            # load before a tick is discarded as "revoked" -- the poller already
            # de-duplicates overlapping runs itself via a Redis lock
            # (worker/poller.py), so this only needs to bound unbounded queue
            # growth, not enforce freshness.
            "options": {
                "queue": "poller",
                "expires": max(config.EVAL_POLL_INTERVAL_SECONDS * 10, 30),
            },
        },
    },
)

# NOTE: ``submit_evaluation`` has no static route — callers pass ``queue=`` at
# dispatch time ("student_submit" for live submits, "bulk_contest_evaluation" for
# bulk runs) so the interactive and bulk paths land on isolated queues.


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
