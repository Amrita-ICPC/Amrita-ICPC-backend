# app/scheduler.py
from time import timezone
from app.core.config import config
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore


def create_scheduler() -> AsyncIOScheduler:
    """
    Create and configure an asynchronous job scheduler.

    The scheduler is configured with a SQLAlchemy job store using the configured
    database URL, UTC timezone, and defaults for misfire handling.

    Returns:
        AsyncIOScheduler: The configured asynchronous scheduler instance.
    """
    jobstores = {
        "default": SQLAlchemyJobStore(url=config.DATABASE_URL)
    }

    scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        timezone="UTC",
        job_defaults={
            "misfire_grace_time": 60,  # if server was down, fire if <= 60s late
            "coalesce": True           # if multiple misfires, run only once
        }
    )
    
    return scheduler

scheduler = create_scheduler()