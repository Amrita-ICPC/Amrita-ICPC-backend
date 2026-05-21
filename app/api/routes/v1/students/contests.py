#TODO: Implement RBAC auth gaurd
from app.schema.student.contest_team import ContestTeamUpdate
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
from app.core.guards.team_student import TeamStudentGuard
from app.repositories.student.team import StudentTeamRepository
from app.repositories.student.contest_team import ContestTeamRepository
from app.service.student.contest_team import ContestTeamService
from app.schema.team import ContestTeamImport
from app.core.logger import logger

router = APIRouter()


def get_student_contest_service(
    db: AsyncSession = Depends(get_db),
) -> StudentContestService:
    repository = StudentContestRepository(db)
    contest_repository = ContestRepository(db)
    team_repository = TeamRepository(db)
    contest_student_guard = ContestStudentGuard(db)
    return StudentContestService(repository,contest_repository,team_repository,contest_student_guard)

def get_contest_team_service(
    db: AsyncSession = Depends(get_db),
) -> ContestTeamService:
    repository = ContestTeamRepository(db)
    team_repository = StudentTeamRepository(db)
    team_student_guard = TeamStudentGuard(db)
    contest_repository = ContestRepository(db)
    contest_student_guard = ContestStudentGuard(db)
    return ContestTeamService(
        repository=repository,
        team_repository=team_repository,
        team_student_guard=team_student_guard,
        contest_repository=contest_repository,
        contest_student_guard=contest_student_guard,
    )

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

@router.post(
    "/{contest_id}/teams/import",
    response_model=APIResponse[None],
    summary="Import an existing student team into a contest",
)
async def import_student_team(
    request: Request,
    contest_id: UUID,
    contest_team_import: ContestTeamImport,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestTeamService = Depends(get_contest_team_service),
):
    """
    Import an existing team and its members into the specified contest.
    """
    await service.import_team(
        contest_id=contest_id,
        contest_team_import=contest_team_import,
        user_id=user_id,
    )
    logger.info(f"Successfully imported team {contest_team_import.team_id} into contest {contest_id} by user {user_id}")
    return create_api_response(
        request,
        data=None,
        message="Team imported into contest successfully",
    )


@router.patch(
    "/{contest_id}/teams/{contest_team_id}",
    response_model=APIResponse[None],
    summary="Update a contest team",
)
async def update_contest_team(
    request: Request,
    contest_id: UUID,
    contest_team_id: UUID,
    contest_team_update: ContestTeamUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: ContestTeamService = Depends(get_contest_team_service),
):
    """
    Update a contest team.
    """
    await service.update_contest_team(
        contest_team_id=contest_team_id,
        contest_team_update=contest_team_update,
        user_id=user_id,
    )
    logger.info(f"Successfully updated team {contest_team_id} in contest {contest_id} by user {user_id}")
    return create_api_response(
        request,
        data=None,
        message="Team updated successfully",
    )

