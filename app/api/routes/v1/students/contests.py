#TODO: Implement RBAC auth gaurd
from app.core.guards.contest_student import ContestStudentGuard
from app.repositories.team import TeamRepository
from app.repositories.contest import ContestRepository
from app.schema.student.contests import (
    StudentContestRegistrationRequest, 
    StudentContestListResponse, 
    StudentContestDetailsResponse,
    StudentContestStatusResponse
)
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user_id
from app.core.clients.database import get_db
from app.core.response import create_api_response
from app.repositories.student.contest import StudentContestRepository
from app.repositories.dto.pagination import PaginationParams
from app.schema.base import APIResponse
from app.service.student.contests import StudentContestService
from app.utils.pagination import get_pagination

router = APIRouter()


def get_student_contest_service(
    db: AsyncSession = Depends(get_db),
) -> StudentContestService:
    repository = StudentContestRepository(db)
    contest_repository = ContestRepository(db)
    team_repository = TeamRepository(db)
    contest_student_guard = ContestStudentGuard(db)
    return StudentContestService(repository,contest_repository,team_repository,contest_student_guard)


@router.get(
    "/",
    response_model=APIResponse[StudentContestListResponse],
    summary="Get available contests for student",
)
async def get_student_contests(
    request: Request,
    filters: StudentContestRegistrationRequest = Depends(),
    search: str | None = Query(None, description="Search by contest name"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
):
    """
    Get all published contests available to the student.
    Filter by registration status and contest run status.
    """
    pagination_params = PaginationParams(
        skip=(page - 1) * page_size,
        limit=page_size,
    )

    result = await service.get_all_contests(
        user_id=user_id,
        request=filters,
        search=search,
        pagination=pagination_params,
    )

    return create_api_response(
        request,
        data=result,
        message="Student contests fetched successfully",
    )

@router.get(
    "/{contest_id}",
    response_model=APIResponse[StudentContestDetailsResponse],
    summary="Get contest details for student",
)
async def get_student_contest_by_id(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
):
    """
    Get contest details for student.
    """
    result = await service.get_contest_by_id(contest_id, user_id)
    return create_api_response(
        request,
        data=result,
        message="Student contest details fetched successfully",
    )

@router.get(
    "/{contest_id}/participation/me",
    response_model=APIResponse[StudentContestStatusResponse],
    summary="Get student participation status in a contest",
)
async def get_student_contest_status(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
):
    """
    Get student participation status in a contest, including team details and readiness.
    """
    result = await service.get_student_status_in_contest(contest_id, user_id)
    return create_api_response(
        request,
        data=result,
        message="Student contest status fetched successfully",
    )
