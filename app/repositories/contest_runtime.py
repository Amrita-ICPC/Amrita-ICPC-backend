from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.contest import ContestRuntimeNotFoundError
from app.models.contest import ContestRuntime


class ContestRuntimeRepository:
    """
    Repository for contest runtime database operations.

    Attributes:
        db: The asynchronous database session.
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize the ContestRuntimeRepository.

        Args:
            db: The asynchronous database session.
        """
        self.db = db

    async def get_contest_runtime_by_id(
        self, contest_id: UUID
    ) -> ContestRuntime | None:
        """
        Fetch a single contest runtime by its contest ID.

        Args:
            contest_id: The UUID of the contest.

        Returns:
            ContestRuntime | None: The contest runtime if found, otherwise None.
        """
        result = await self.db.execute(
            select(ContestRuntime).where(ContestRuntime.contest_id == contest_id)
        )
        return result.scalars().one_or_none()

    async def get_contest_runtime_or_raise(self, contest_id: UUID) -> ContestRuntime:
        """
        Fetch a single contest runtime by its contest ID or raise if not found.

        Args:
            contest_id: The UUID of the contest.

        Returns:
            ContestRuntime: The contest runtime instance.

        Raises:
            ContestRuntimeNotFoundError: If the runtime is not found.
        """
        runtime = await self.get_contest_runtime_by_id(contest_id)
        if not runtime:
            raise ContestRuntimeNotFoundError(str(contest_id))
        return runtime

    async def create_contest_runtime(
        self, contest_runtime: ContestRuntime
    ) -> ContestRuntime:
        """
        Create a new contest runtime in the database.

        Args:
            contest_runtime: The ContestRuntime model instance to create.

        Returns:
            ContestRuntime: The created contest runtime instance.
        """
        self.db.add(contest_runtime)
        await self.db.flush()
        return contest_runtime

    async def update_contest_runtime(
        self, contest_runtime: ContestRuntime
    ) -> ContestRuntime:
        """
        Update an existing contest runtime.

        Args:
            contest_runtime: The ContestRuntime model instance to update.

        Returns:
            ContestRuntime: The updated contest runtime instance.
        """
        await self.db.flush()
        return contest_runtime
