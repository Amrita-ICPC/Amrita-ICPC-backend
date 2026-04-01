from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions.database import DatabaseUnavailableError
from app.repositories.health import HealthRepository

if TYPE_CHECKING:
    from app.service.health_service import HealthService


@pytest.fixture
def mock_health_repository() -> MagicMock:
    """Provide a mocked health repository."""
    repository = MagicMock(spec=HealthRepository)
    repository.ping = AsyncMock()
    return repository


@pytest.fixture
def health_service(mock_health_repository: MagicMock) -> "HealthService":
    """Provide a HealthService with mocked dependencies."""
    from app.service.health_service import HealthService

    return HealthService(repository=mock_health_repository)


@pytest.mark.asyncio
async def test_check_database_success(
    health_service: "HealthService", mock_health_repository: MagicMock
) -> None:
    """Test that health check succeeds when repository ping succeeds."""
    await health_service.check_database()

    mock_health_repository.ping.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_check_database_raises_database_unavailable_error(
    health_service: "HealthService", mock_health_repository: MagicMock
) -> None:
    """Test that SQLAlchemy errors are mapped to DatabaseUnavailableError."""
    mock_health_repository.ping.side_effect = SQLAlchemyError("connection lost")

    with pytest.raises(DatabaseUnavailableError) as exc:
        await health_service.check_database()

    assert exc.value.detail == "connection lost"
    mock_health_repository.ping.assert_awaited_once_with()
