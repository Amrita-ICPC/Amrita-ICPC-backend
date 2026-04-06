import logging

from sqlalchemy.exc import SQLAlchemyError

from app.exceptions.database import DatabaseUnavailableError
from app.repositories.health import HealthRepository

logger = logging.getLogger(__name__)


class HealthService:
    """Service layer for Application Health Monitoring."""

    def __init__(self, repository: HealthRepository):
        self.repository = repository

    async def check_database(self) -> None:
        """Ping the database to verify connectivity.

        Raises:
            DatabaseUnavailableError: If the execution fails or connection drops.
        """
        try:
            await self.repository.ping()
        except SQLAlchemyError as e:
            logger.exception("Database health check failed")
            raise DatabaseUnavailableError(detail="Database unavailable") from e
