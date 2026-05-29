# app/scheduler.py

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import config
from app.core.logger import logger


def create_scheduler() -> AsyncIOScheduler:
    """
    Create and configure an asynchronous job scheduler.

    The scheduler is configured with a SQLAlchemy job store using the configured
    database URL, UTC timezone, and defaults for misfire handling.

    Returns:
        AsyncIOScheduler: The configured asynchronous scheduler instance.
    """
    jobstores = {"default": SQLAlchemyJobStore(url=config.DATABASE_URL)}

    scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        timezone="UTC",
        job_defaults={
            "misfire_grace_time": 60,  # if server was down, fire if <= 60s late
            "coalesce": True,  # if multiple misfires, run only once
        },
    )

    return scheduler


def job_error_listener(event):
    logger.error(
        "Scheduler job failed",
        extra={
            "job_id": event.job_id,
            "scheduled_run_time": str(event.scheduled_run_time),
        },
    )


scheduler = create_scheduler()

scheduler.add_listener(
    job_error_listener,
    EVENT_JOB_ERROR,
)
