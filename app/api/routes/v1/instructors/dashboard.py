from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    get_current_user_id,
    instructor_manager_admin_procedure,
)
from app.core.clients.database import get_db
from app.core.response import create_api_response
from app.repositories.bank import BankRepository
from app.repositories.contest import ContestRepository
from app.repositories.user import UserRepository
from app.schema.base import APIResponse
from app.schema.instructor_dashboard import InstructorDashboardResponse
from app.service.bank_service import BankService
from app.service.instructor_dashboard_service import InstructorDashboardService
from app.validators.bank import BankValidator

router = APIRouter()


def get_instructor_dashboard_service(
    db: AsyncSession = Depends(get_db),
) -> InstructorDashboardService:
    """
    Dependency injector linking repositories/services into the dashboard service.

    Reuses BankRepository/BankValidator/BankService exactly as the bank routes
    do, so recent-bank visibility and sorting can never drift from the
    existing bank listing endpoint.
    """
    contest_repository = ContestRepository(db)
    user_repository = UserRepository(db)
    bank_service = BankService(BankRepository(db), BankValidator())
    return InstructorDashboardService(
        contest_repository=contest_repository,
        user_repository=user_repository,
        bank_service=bank_service,
    )


@router.get(
    "/dashboard",
    response_model=APIResponse[InstructorDashboardResponse],
    summary="Get the instructor dashboard overview",
    dependencies=[instructor_manager_admin_procedure],
)
async def get_instructor_dashboard(
    request: Request,
    contest_limit: int = Query(
        5,
        ge=1,
        le=20,
        description="Max contests to return per run-status group (live/upcoming/completed)",
    ),
    bank_limit: int = Query(
        4,
        ge=1,
        le=20,
        description="Max recent question banks to return",
    ),
    user_id: UUID = Depends(get_current_user_id),
    service: InstructorDashboardService = Depends(get_instructor_dashboard_service),
):
    """
    Get the instructor dashboard: contest summary counts, actionable
    attention items (pending approvals, missing questions, pending
    evaluations, results ready to publish), live/upcoming/completed contest
    groups, and recent question banks.

    Contests are scoped to those the requesting user created or is assigned
    to as an instructor (or every contest, for admins) -- the same visibility
    rule already enforced by the main contest listing endpoint.
    """
    result = await service.get_dashboard(
        user_id=user_id,
        contest_limit=contest_limit,
        bank_limit=bank_limit,
    )
    return create_api_response(
        request,
        data=result,
        message="Instructor dashboard fetched successfully",
    )
