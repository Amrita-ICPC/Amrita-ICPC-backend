from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class HealthRepository:
    """Repository for health-related database probes."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ping(self) -> None:
        """Execute a lightweight database probe to verify connectivity."""
        await self.db.execute(text("SELECT 1"))
