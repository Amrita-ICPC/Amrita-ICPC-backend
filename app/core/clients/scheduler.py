# app/scheduler.py
from time import timezone
from app.core.config import config
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore


def create_scheduler() -> AsyncIOScheduler:
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