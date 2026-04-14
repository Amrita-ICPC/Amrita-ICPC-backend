"""Student API routes module.

Combines student endpoints for:
- Contest management
- Team management  
- Code execution
"""

from fastapi import APIRouter

from app.api.routes.v1.students import contests, teams, run

# Combined router for all student endpoints
router = APIRouter()
router.include_router(contests.router)
router.include_router(teams.router)
router.include_router(run.router)

__all__ = ["router"]
