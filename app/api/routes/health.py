from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clients.database import get_db
from app.repositories.health import HealthRepository
from app.service.health_service import HealthService

router = APIRouter()


def get_health_service(db: AsyncSession = Depends(get_db)) -> HealthService:
    """Build a health service with repository dependencies."""
    return HealthService(repository=HealthRepository(db=db))


@router.get("/health")
async def health_check(service: HealthService = Depends(get_health_service)):
    """Execute a system health check monitored against active database connections natively."""
    await service.check_database()
    return {"status": "ok", "database": "connected"}
