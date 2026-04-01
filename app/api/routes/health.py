from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clients.database import get_db
from app.service.health_service import HealthService

router = APIRouter()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Execute a system health check monitored against active database connections natively."""
    await HealthService.check_database(db)
    return {"status": "ok", "database": "connected"}
