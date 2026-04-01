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
from app.repositories.team import TeamRepository
from app.schema.base import APIResponse
from app.schema.team import (
    ContestTeamResponse,
    TeamCreate,
    TeamMemberAdd,
    TeamMemberRemove,
    TeamMemberResponse,
    TeamUpdate,
)
from app.service.team_service import TeamService
from app.utils.enums import TeamStatus
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
        guard=TeamOperationGuard(db),
        validator=TeamValidator(),
    )


@router.post(
    "/contests/{contest_id}/teams",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a team in a contest",
    dependencies=[can_update("contests")],
)
async def create_team(
    request: Request,
    contest_id: UUID,
    team_data: TeamCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: TeamService = Depends(get_team_service),
):
    """
    Create a new team in a specific contest.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        team_data (TeamCreate): The team data to create.
        user_id (UUID): Authenticated user ID.
        service (TeamService): Injected domain service.

    Returns:
        APIResponse: Standardized response encapsulating creation metadata.
    """
    team = await service.create_team(contest_id, team_data, user_id)
    logger.info(
        f"Team '{team_data.name}' created in contest {contest_id} by user {user_id}"
    )

    return create_api_response(
        request,
        data=team,
        message="Team created successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.patch(
    "/contests/{contest_id}/teams/{team_id}",
    response_model=APIResponse[ContestTeamResponse],
    summary="Update a team in a contest",
    dependencies=[can_update("teams")],
)
async def update_team(
    request: Request,
    contest_id: UUID,
    team_id: UUID,
    team_data: TeamUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: TeamService = Depends(get_team_service),
):
    """
    Update an existing team in a contest.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        team_id (UUID): The unique identifier of the team.
        team_data (TeamUpdate): The fields to update.
        user_id (UUID): Authenticated user ID.
        service (TeamService): Injected domain service.

    Returns:
        APIResponse: Standardized response encapsulating updated team data.
    """
    team = await service.update_team(contest_id, team_id, team_data, user_id)
    logger.info(f"Team '{team.name}' updated in contest {contest_id} by user {user_id}")
    return create_api_response(request, data=team, message="Team updated successfully")


@router.get(
    "/contests/{contest_id}/teams",
    response_model=APIResponse[list[ContestTeamResponse]],
    summary="Get all teams in a contest",
    dependencies=[can_read("contests")],
)
async def get_contest_teams(
    request: Request,
    contest_id: UUID,
    search: str | None = Query(None, description="Search by team name"),
    team_status: TeamStatus | None = Query(None, description="Filter by team status"),
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
    total, teams = await service.get_contest_teams(
        contest_id, user_id, search, team_status, skip, page_size
    )

    pagination = get_pagination(total=total, page=page, page_size=page_size)

    return create_api_response(
        request,
        data=teams,
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
    "/contests/{contest_id}/teams/{team_id}/members",
    response_model=APIResponse[list[TeamMemberResponse]],
    summary="Get team members",
    dependencies=[can_read("contests")],
)
async def get_team_members(
    request: Request,
    contest_id: UUID,
    team_id: UUID,
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
        team_id (UUID): The unique identifier of the team.
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
        contest_id, team_id, user_id, search, skip, page_size
    )

    pagination = get_pagination(total=total, page=page, page_size=page_size)

    return create_api_response(
        request,
        data=members,
        message="Team members fetched successfully",
        pagination=pagination,
    )


@router.post(
    "/contests/{contest_id}/teams/{team_id}/members",
    response_model=APIResponse[list[TeamMemberResponse]],
    summary="Add members to a team",
    dependencies=[can_update("teams")],
)
async def add_team_members(
    request: Request,
    contest_id: UUID,
    team_id: UUID,
    member_data: TeamMemberAdd,
    user_id: UUID = Depends(get_current_user_id),
    service: TeamService = Depends(get_team_service),
):
    """
    Add members to an existing team.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        team_id (UUID): The unique identifier of the team.
        member_data (TeamMemberAdd): Request containing list of member IDs.
        user_id (UUID): Authenticated user ID.
        service (TeamService): Injected domain service.

    Returns:
        APIResponse: Success confirmation with updated member list.
    """
    _, members = await service.add_team_members(
        contest_id, team_id, member_data, user_id
    )
    logger.info(
        f"Added {len(member_data.member_ids)} members to team {team_id} "
        f"in contest {contest_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=members,
        message="Members added successfully",
    )


@router.delete(
    "/contests/{contest_id}/teams/{team_id}/members",
    response_model=APIResponse[list[TeamMemberResponse]],
    summary="Remove members from a team",
    dependencies=[can_update("teams")],
)
async def remove_team_member(
    request: Request,
    contest_id: UUID,
    team_id: UUID,
    member_data: TeamMemberRemove,
    user_id: UUID = Depends(get_current_user_id),
    service: TeamService = Depends(get_team_service),
):
    """
    Remove members from an existing team.

    Args:
        request (Request): Framework context.
        contest_id (UUID): The unique identifier of the contest.
        team_id (UUID): The unique identifier of the team.
        member_data (TeamMemberRemove): Request containing list of member IDs to remove.
        user_id (UUID): Authenticated user ID.
        service (TeamService): Injected domain service.

    Returns:
        APIResponse: Success confirmation with updated member list.
    """
    _, members = await service.remove_team_member(
        contest_id, team_id, member_data, user_id
    )
    logger.info(
        f"Removed {len(member_data.member_ids)} members from team {team_id} "
        f"in contest {contest_id} by user {user_id}"
    )
    return create_api_response(
        request,
        data=members,
        message="Members removed successfully",
    )
