from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.contest import ContestRuntime


class ContestRuntimeRepository:
    """Repository for contest runtime database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_contest_runtime_by_id(self, contest_id: UUID) -> ContestRuntime | None:
        """Fetch a single contest runtime by its contest ID."""
        result = await self.db.execute(
            select(ContestRuntime).where(ContestRuntime.contest_id == contest_id)
        )
        return result.scalars().one_or_none()

    async def create_contest_runtime(self, contest_runtime: ContestRuntime) -> ContestRuntime:
        """Create a new contest runtime in the database."""
        self.db.add(contest_runtime)
        await self.db.flush()
        return contest_runtime

    async def update_contest_runtime(self, contest_runtime: ContestRuntime) -> ContestRuntime:
        """Update an existing contest runtime."""
        await self.db.flush()
        return contest_runtime
