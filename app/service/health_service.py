import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.database import DatabaseUnavailableError

logger = logging.getLogger(__name__)


class HealthService:
    """Service layer for Application Health Monitoring."""

    @staticmethod
    async def check_database(db: AsyncSession) -> None:
        """Ping the database to verify connectivity.

        Args:
            db (AsyncSession): The active database session injected via dependency.

        Raises:
            DatabaseUnavailableError: If the execution fails or connection drops.
        """
        try:
            await db.execute(text("SELECT 1"))
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            raise DatabaseUnavailableError(detail=str(e))
