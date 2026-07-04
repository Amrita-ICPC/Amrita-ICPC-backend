"""Instructor API routes module.

Combines instructor-facing endpoints for:
- Dashboard overview
"""

from fastapi import APIRouter

from app.api.routes.v1.instructors import dashboard

# Combined router for all instructor endpoints
router = APIRouter()
router.include_router(dashboard.router)

__all__ = ["router"]
