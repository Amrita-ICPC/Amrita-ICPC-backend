from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    can_read,
    can_update,
    get_current_user,
)
from app.core.clients.database import get_db
from app.core.guards.team import TeamOperationGuard
from app.core.logger import logger
from app.repositories.team import TeamRepository
from app.schema.contest import MessageResponse
from app.schema.team import (
    ContestTeamResponse,
    TeamCreate,
    TeamListResponse,
    TeamMemberAdd,
    TeamMemberRemove,
    TeamMembersResponse,
    TeamUpdate,
)
from app.service.team_service import TeamService
from app.service.user_service import UserService
from app.utils.enums import TeamStatus
from app.validators.team import TeamValidator

router = APIRouter()


def get_team_service(db: Session = Depends(get_db)) -> TeamService:
    return TeamService(
        repository=TeamRepository(db),
        guard=TeamOperationGuard(db),
        validator=TeamValidator(),
    )


@router.post(
    "/contests/{contest_id}/teams",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a team in a contest",
    dependencies=[can_update("contests")],
)
async def create_team(
    contest_id: UUID,
    team_data: TeamCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Create a new team in a contest.

    Only users with permission to manage the contest (admin/instructor) can create teams.

    Args:
        contest_id: Contest ID
        team_data: Team creation data
        db: Database session
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        Success message

    Raises:
        ContestNotFoundError: If contest not found
        PermissionDeniedError: If user doesn't have permission
        TeamAlreadyExistsError: If team name already exists
        InvalidTeamSizeError: If team size is invalid
        UserNotFoundError: If any member not found
    """
    kc_id = current_user.get("sub")
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id
    await service.create_team(contest_id, team_data, user_id)
    logger.info(
        f"Team '{team_data.name}' created in contest {contest_id} by user {user_id}"
    )

    return MessageResponse(message="Team created successfully")


@router.patch(
    "/contests/{contest_id}/teams/{team_id}",
    response_model=ContestTeamResponse,
    summary="Update a team in a contest",
    dependencies=[can_update("teams")],
)
async def update_team(
    contest_id: UUID,
    team_id: UUID,
    team_data: TeamUpdate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Update a team in a contest.

    Only allows updating basic team information (name, description, logo, status).
    Members management should be handled through separate endpoints.

    Args:
        contest_id: Contest ID
        team_id: Team ID to update
        team_data: Team update data
        db: Database session
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        Updated team object

    Raises:
        PermissionDeniedError: If user doesn't have permission
        ContestNotFoundError: If contest not found
        TeamNotFoundError: If team not found
        TeamAlreadyExistsError: If updated name conflicts
    """
    kc_id = current_user.get("sub")
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id

    team = await service.update_team(contest_id, team_id, team_data, user_id)
    logger.info(f"Team '{team.name}' updated in contest {contest_id} by user {user_id}")
    return team


@router.get(
    "/contests/{contest_id}/teams",
    response_model=TeamListResponse,
    summary="Get all teams in a contest",
    dependencies=[can_read("contests")],
)
async def get_contest_teams(
    contest_id: UUID,
    search: str | None = Query(None, description="Search by team name"),
    status: TeamStatus | None = Query(None, description="Filter by team status"),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of teams per page"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Get all teams in a contest with pagination, search, and filtering.

    Args:
        contest_id: Contest ID
        search: Optional search term for team name
        status: Optional status to filter by
        page: Page number (starts from 1)
        page_size: Number of teams per page (max 100)
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        List of teams and total count
    """
    kc_id = current_user.get("sub")
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id
    skip = (page - 1) * page_size
    total, teams = await service.get_contest_teams(
        contest_id, user_id, search, status, skip, page_size
    )
    return TeamListResponse(total=total, page=page, page_size=page_size, teams=teams)


@router.get(
    "/contests/{contest_id}/teams/{team_id}",
    response_model=ContestTeamResponse,
    summary="Get team by ID",
    dependencies=[can_read("contests")],
)
async def get_team(
    contest_id: UUID,
    team_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Get a specific team in a contest.

    Args:
        contest_id: Contest ID
        team_id: Team ID
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        Team details

    Raises:
        ContestNotFoundError: If contest not found
        TeamNotFoundError: If team not found in contest
    """
    kc_id = current_user.get("sub")
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id
    return await service.get_team_by_id(contest_id, team_id, user_id)


@router.get(
    "/contests/{contest_id}/teams/{team_id}/members",
    response_model=TeamMembersResponse,
    summary="Get team members",
    dependencies=[can_read("contests")],
)
async def get_team_members(
    contest_id: UUID,
    team_id: UUID,
    search: str | None = Query(None, description="Search by member name or email"),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of members per page"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Get all members of a team with pagination and search functionality.

    Supports searching by member name or email address and provides
    pagination for teams with large member counts.

    Args:
        contest_id: Contest UUID containing the team
        team_id: Team UUID to get members from
        search: Optional search term for member name or email
        page: Page number starting from 1
        page_size: Number of members per page (max 100)
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        TeamMembersResponse with member list, pagination info, and team details

    Raises:
        ContestNotFoundError: If contest not found
        TeamNotFoundError: If team not found in contest
        PermissionDeniedError: If user lacks read permission on contest
    """
    kc_id = current_user.get("sub")
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id
    skip = (page - 1) * page_size

    return await service.get_team_members(
        contest_id, team_id, user_id, search, skip, page_size
    )


@router.post(
    "/contests/{contest_id}/teams/{team_id}/members",
    response_model=TeamMembersResponse,
    summary="Add members to a team",
    dependencies=[can_update("teams")],
)
async def add_team_members(
    contest_id: UUID,
    team_id: UUID,
    member_data: TeamMemberAdd,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Add new members to an existing team in a contest.

    Validates member eligibility, prevents duplicate memberships, and
    enforces team size constraints. Can optionally update team leadership.

    Args:
        contest_id: Contest UUID containing the team
        team_id: Team UUID to add members to
        member_data: TeamMemberAdd with member IDs and optional new leader
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        TeamMembersResponse with updated member list and team information

    Raises:
        ContestNotFoundError: If contest not found
        TeamNotFoundError: If team not found in contest
        PermissionDeniedError: If user lacks team management permission
        UserNotFoundError: If any specified member not found
        MemberAlreadyInTeamError: If member already in team
        InvalidTeamSizeError: If adding would exceed team size limit
    """
    kc_id = current_user.get("sub")
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id

    result = await service.add_team_members(contest_id, team_id, member_data, user_id)
    logger.info(
        f"Added {len(member_data.member_ids)} members to team {team_id} "
        f"in contest {contest_id} by user {user_id}"
    )
    return result


@router.delete(
    "/contests/{contest_id}/teams/{team_id}/members",
    response_model=TeamMembersResponse,
    summary="Remove members from a team",
    dependencies=[can_update("teams")],
)
async def remove_team_member(
    contest_id: UUID,
    team_id: UUID,
    member_data: TeamMemberRemove,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Remove multiple members from a team in a contest.

    Handles team leadership succession when removing the current leader.
    Validates minimum team size requirements for confirmed teams.

    Args:
        contest_id: Contest UUID containing the team
        team_id: Team UUID to remove members from
        member_data: TeamMemberRemove with member IDs and optional new leader
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        TeamMembersResponse with updated member list and team information

    Raises:
        ContestNotFoundError: If contest not found
        TeamNotFoundError: If team not found in contest
        PermissionDeniedError: If user lacks team management permission
        MemberNotInTeamError: If any member not in team
        CannotRemoveTeamLeaderError: If removing leader without replacement
        InvalidTeamSizeError: If removal would violate minimum team size
    """
    kc_id = current_user.get("sub")
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id

    result = await service.remove_team_member(contest_id, team_id, member_data, user_id)
    logger.info(
        f"Removed {len(member_data.member_ids)} members from team {team_id} "
        f"in contest {contest_id} by user {user_id}"
    )
    return result
