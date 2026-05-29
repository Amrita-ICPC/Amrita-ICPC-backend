from datetime import datetime, timezone
from uuid import UUID

from app.core.clients.database import SessionLocal
from app.exceptions.contest import ContestNotFoundError
from app.models.contest import ContestRuntime
from app.utils.enums import ContestRuntimeStatus


class ContestJobs:
    """Background jobs related to contest management and execution."""

    @staticmethod
    async def auto_start_contest(contest_id: UUID) -> None:
        """
        Automatically start a scheduled contest.

        Updates the contest runtime status to RUNNING.

        Args:
            contest_id: The UUID of the contest to start.

        Raises:
            ContestNotFoundError: If no contest runtime is found for the given ID.
        """
        async with SessionLocal() as db:
            run_time: ContestRuntime | None = await db.get(ContestRuntime, contest_id)

            if not run_time:
                raise ContestNotFoundError(str(id))

            if run_time.runtime_status != ContestRuntimeStatus.SCHEDULED:
                return

            run_time.runtime_status = ContestRuntimeStatus.RUNNING
            run_time.updated_at = datetime.now(timezone.utc)
            db.add(run_time)
            await db.commit()

    @staticmethod
    async def finish_contest(contest_id: UUID) -> None:
        """
        Finish an active contest.

        Updates the contest runtime status to FINISHED and sets the finish time.

        Args:
            contest_id: The UUID of the contest to finish.
        """
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
