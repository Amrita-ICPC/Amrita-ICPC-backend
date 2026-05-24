from app.repositories.contest import ContestRepository
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    can_read,
    can_update,
    get_current_user_id,
)
from app.core.clients.database import get_db
from app.core.guards.team import TeamOperationGuard
from app.core.logger import logger
from app.core.response import create_api_response
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.team import TeamRepository
from app.repositories.user import UserRepository
from app.schema.base import APIResponse
from app.schema.team import (
    ContestTeamResponse,
    TeamListResponse,
    TeamMemberAdd,
    TeamMemberRemove,
    TeamMemberResponse,
)
from app.service.team_service import TeamService
from app.utils.enums import TeamApprovalStatus, TeamStatus
from app.utils.pagination import get_pagination
from app.validators.team import TeamValidator

router = APIRouter()


def get_team_service(db: AsyncSession = Depends(get_db)) -> TeamService:
    """
    Dependency injector linking repository, guard, and validator into the service.

    Args:
        db (Session): Database session passed from FastAPI dependencies.

    Returns:
        TeamService: Fully configured service class instance.
    """
    return TeamService(
        repository=TeamRepository(db),
        contest_team_repository=ContestTeamRepository(db),
        guard=TeamOperationGuard(db),
        validator=TeamValidator(),
        contest_repository=ContestRepository(db),
    )


@router.patch(
    "/contests/{contest_id}/teams/{team_id}/approve",
    response_model=APIResponse[ContestTeamResponse],
    summary="Approve a team in a contest",
    dependencies=[can_update("teams")],
)
async def approve_team(
    request: Request,
    contest_id: UUID,
    team_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: TeamService = Depends(get_team_service),
):
    """
    Approve a contest team.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        team_id (UUID): The unique identifier of the team.
        user_id (UUID): Authenticated user ID.
        service (TeamService): Injected domain service.

    Returns:
        APIResponse: Standardized response encapsulating the updated team data.
    """
    team = await service.approve_team(contest_id, team_id, user_id)
    logger.info(f"Team {team_id} approved in contest {contest_id} by user {user_id}")
    return create_api_response(request, data=team, message="Team approved successfully")


@router.patch(
    "/contests/{contest_id}/teams/{team_id}/reject",
    response_model=APIResponse[ContestTeamResponse],
    summary="Reject a team in a contest",
    dependencies=[can_update("teams")],
)
async def reject_team(
    request: Request,
    contest_id: UUID,
    team_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: TeamService = Depends(get_team_service),
):
    """
    Reject a contest team.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        team_id (UUID): The unique identifier of the team.
        user_id (UUID): Authenticated user ID.
        service (TeamService): Injected domain service.

    Returns:
        APIResponse: Standardized response encapsulating the updated team data.
    """
    team = await service.reject_team(contest_id, team_id, user_id)
    logger.info(f"Team {team_id} rejected in contest {contest_id} by user {user_id}")
    return create_api_response(request, data=team, message="Team rejected successfully")


@router.patch(
    "/contests/{contest_id}/teams/{team_id}/disqualify",
    response_model=APIResponse[ContestTeamResponse],
    summary="Disqualify a team in a contest",
    dependencies=[can_update("teams")],
)
async def disqualify_team(
    request: Request,
    contest_id: UUID,
    team_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: TeamService = Depends(get_team_service),
):
    """
    Disqualify a contest team.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        team_id (UUID): The unique identifier of the team.
        user_id (UUID): Authenticated user ID.
        service (TeamService): Injected domain service.

    Returns:
        APIResponse: Standardized response encapsulating the updated team data.
    """
    team = await service.disqualify_team(contest_id, team_id, user_id)
    logger.info(
        f"Team {team_id} disqualified in contest {contest_id} by user {user_id}"
    )
    return create_api_response(
        request, data=team, message="Team disqualified successfully"
    )


@router.get(
    "/contests/{contest_id}/teams",
    response_model=APIResponse[TeamListResponse],
    summary="Get all teams in a contest",
    dependencies=[can_read("contests")],
)
async def get_contest_teams(
    request: Request,
    contest_id: UUID,
    search: str | None = Query(None, description="Search by team name"),
    team_status: TeamStatus | None = Query(None, description="Filter by team status"),
    approval_status: TeamApprovalStatus | None = Query(
        None, description="Filter by approval status"
    ),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of teams per page"),
    user_id: UUID = Depends(get_current_user_id),
    service: TeamService = Depends(get_team_service),
):
    """
    Get all teams in a specific contest.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        search (str | None): Optional string to search team names.
        team_status (TeamStatus | None): Optional filter for team status.
        page (int): Page number (starts from 1).
        page_size (int): Number of teams per page.
        user_id (UUID): Authenticated user ID.
        service (TeamService): Injected domain service.

    Returns:
        APIResponse: Standardized response with list of teams and pagination state.
    """
    skip = (page - 1) * page_size
    team_list = await service.get_contest_teams(
        contest_id, user_id, search, team_status, approval_status, skip, page_size
    )

    pagination = get_pagination(total=team_list.total, page=page, page_size=page_size)

    return create_api_response(
        request,
        data=team_list,
        message="Teams fetched successfully",
        pagination=pagination,
    )


@router.get(
    "/contests/{contest_id}/teams/{team_id}",
    response_model=APIResponse[ContestTeamResponse],
    summary="Get team by ID",
    dependencies=[can_read("contests")],
)
async def get_team(
    request: Request,
    contest_id: UUID,
    team_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: TeamService = Depends(get_team_service),
):
    """
    Get detailed information about a specific team.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        team_id (UUID): The unique identifier of the team.
        user_id (UUID): Authenticated user ID.
        service (TeamService): Injected domain service.

    Returns:
        APIResponse: Standardized response encapsulating team details.
    """
    team = await service.get_team_by_id(contest_id, team_id, user_id)
    return create_api_response(request, data=team, message="Team fetched successfully")


@router.get(
    "/contests/{contest_id}/teams/{contest_team_id}/members",
    response_model=APIResponse[list[TeamMemberResponse]],
    summary="Get team members",
    dependencies=[can_read("contests")],
)
async def get_team_members(
    request: Request,
    contest_id: UUID,
    contest_team_id: UUID,
    search: str | None = Query(None, description="Search by member name or email"),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of members per page"),
    user_id: UUID = Depends(get_current_user_id),
    service: TeamService = Depends(get_team_service),
):
    """
    Get a paginated list of members in a specific team.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        contest_team_id (UUID): The unique identifier of the contest team.
        search (str | None): Optional string to search member names or emails.
        page (int): Page number (starts from 1).
        page_size (int): Number of members per page.
        user_id (UUID): Authenticated user ID.
        service (TeamService): Injected domain service.

    Returns:
        APIResponse: Standardized response with list of members and pagination state.
    """
    skip = (page - 1) * page_size

    total, members = await service.get_team_members(
        contest_id, contest_team_id, user_id, search, skip, page_size
    )

    pagination = get_pagination(total=total, page=page, page_size=page_size)

    return create_api_response(
        request,
        data=members,
        message="Team members fetched successfully",
        pagination=pagination,
    )