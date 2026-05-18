"""Student API routes module.

Combines student endpoints for:
- Contest management
- Team management  
- Code execution
"""

from fastapi import APIRouter

from app.api.routes.v1.students import contests, run, teams

# Combined router for all student endpoints
router = APIRouter()
router.include_router(contests.router, prefix="/contests")
router.include_router(teams.router, prefix="/teams")
router.include_router(run.router, prefix="/run")

__all__ = ["router"]
