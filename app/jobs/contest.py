

from app.repositories.contest_runtime import ContestRuntimeRepository
from datetime import datetime, timezone
from app.utils.enums import ContestRuntimeStatus
from app.exceptions.contest import ContestNotFoundError
from app.core.clients.database import SessionLocal
from uuid import UUID
from app.models.contest import ContestRuntime

class ContestJobs:

    @staticmethod
    async def auto_start_contest(contest_id: UUID):

        async with SessionLocal() as db:
            run_time: ContestRuntime | None = await db.get(
                ContestRuntime,
                contest_id
            )

            if not run_time:
                raise ContestNotFoundError(f"Contest {contest_id} not found")

            if run_time.runtime_status != ContestRuntimeStatus.SCHEDULED:
                return

            run_time.runtime_status = ContestRuntimeStatus.RUNNING
            run_time.updated_at = datetime.now(timezone.utc)
            db.add(run_time)
            await db.commit()

    @staticmethod
    async def finish_contest(contest_id: UUID):

        async with SessionLocal() as db:

            runtime: ContestRuntime | None = await db.get(
                ContestRuntime,
                contest_id,
            )

            if not runtime:
                return

            if runtime.runtime_status != ContestRuntimeStatus.RUNNING:
                return

            runtime.runtime_status = ContestRuntimeStatus.FINISHED
            runtime.finished_at = datetime.now(timezone.utc)
            runtime.updated_at = datetime.now(timezone.utc)

            await db.commit()

            
            
        