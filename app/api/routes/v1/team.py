from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    can_create,
    can_delete,
    can_read,
    can_update,
    get_current_user,
)
from app.core.clients.database import get_db
from app.core.logger import logger
from app.exceptions.auth import PermissionDeniedError
from app.schema.team import (
    AddTeamMemberRequest,
    AddTeamMemberResponse,
    MessageResponse,
    RemoveTeamMemberRequest,
    RemoveTeamMemberResponse,
    TeamCreate,
    TeamListResponse,
    TeamResponse,
    TeamUpdate,
    UserTeamResponse,
)
from app.service.team_service import TeamService
from app.service.user_service import UserService

router = APIRouter()


def get_team_service(db: Session = Depends(get_db)) -> TeamService:
    return TeamService(db)


# Student-facing Team Routes


@router.post(
    "/{contest_id}/team",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new team for this contest",
    dependencies=[can_create("teams")],
)
async def create_team_for_contest(
    contest_id: UUID,
    team: TeamCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Create a new team within a contest.

    Args:
        contest_id: Contest ID
        team: Team creation data (name, description, logo)
        db: Database session
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        Success message

    Raises:
        ContestNotFoundError: If contest not found
        PermissionDeniedError: If user doesn't have permission to create teams
    """
    keycloak_user_id = current_user.get("sub")
    if not keycloak_user_id:
        raise PermissionDeniedError("Invalid authentication: missing user ID")

    user_id = (await UserService.get_user_by_keycloak_id(db, keycloak_user_id)).id

    created_team = await service.create_team(team, contest_id, user_id)
    logger.info(
        f"Team '{created_team.name}' created in contest {contest_id} by user {user_id}"
    )
    return MessageResponse(message="Team created successfully")


@router.get(
    "/{contest_id}/team",
    response_model=TeamResponse | None,
    summary="Check if current user is already registered in a team",
    dependencies=[can_read("teams")],
)
async def get_user_team_in_contest(
    contest_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Get the team that the current user is registered in for this contest.
    Returns null if user is not in any team for this contest.

    Args:
        contest_id: Contest ID
        db: Database session
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        Team object if user is in a team, null otherwise

    Raises:
        ContestNotFoundError: If contest not found
    """
    kc_id = current_user.get("sub")
    user = await UserService.get_user_by_keycloak_id(db, kc_id)

    # Get all teams for user in this contest
    total, teams = await service.get_user_teams(
        user_id=user.id, contest_id=contest_id, skip=0, limit=1
    )

    # Return the first team if found, else None
    return teams[0] if teams else None


@router.get(
    "/{contest_id}/teams",
    response_model=TeamListResponse,
    summary="Get all teams in this contest (Leaderboard)",
    dependencies=[can_read("teams")],
)
async def get_contest_teams_leaderboard(
    contest_id: UUID,
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of teams per page"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Get all teams in a contest with pagination support.
    This is used for displaying the leaderboard.

    Args:
        contest_id: Contest ID
        page: Page number (starts from 1)
        page_size: Number of teams per page (max 100)
        db: Database session
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        List of teams and total count

    Raises:
        ContestNotFoundError: If contest not found
    """
    skip = (page - 1) * page_size
    total, teams = await service.get_contest_teams(
        contest_id=contest_id, skip=skip, limit=page_size
    )
    return TeamListResponse(total=total, teams=teams)


# Team Details and Member Management Routes


@router.get(
    "/{contest_id}/teams/{team_id}",
    response_model=TeamResponse,
    summary="Get team in contest",
    dependencies=[can_read("teams")],
)
async def get_team(
    contest_id: UUID,
    team_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Get a specific team in a contest by ID.

    Args:
        contest_id: Contest ID
        team_id: Team ID
        service: Team service instance

    Returns:
        Team details

    Raises:
        TeamNotFoundError: If team not found or doesn't belong to contest
    """
    team = await service.get_team_by_id(team_id, contest_id)
    return team


@router.patch(
    "/{contest_id}/team/{team_id}",
    response_model=MessageResponse,
    summary="Update team",
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
    Partially update an existing team.

    Args:
        contest_id: Contest ID
        team_id: Team ID
        team_data: Team update data
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        Success message

    Raises:
        TeamNotFoundError: If team not found or doesn't belong to contest
        PermissionDeniedError: If user not authenticated
    """
    keycloak_user_id = current_user.get("sub")
    if not keycloak_user_id:
        raise PermissionDeniedError("Invalid authentication: missing user ID")

    user_id = (await UserService.get_user_by_keycloak_id(db, keycloak_user_id)).id

    await service.update_team(team_id, team_data, contest_id, user_id)
    logger.info(f"Team with ID {team_id} updated by user {user_id}")

    return MessageResponse(message="Team updated successfully")


@router.delete(
    "/{contest_id}/team/{team_id}",
    response_model=MessageResponse,
    summary="Delete team from contest",
    dependencies=[can_delete("teams")],
)
async def delete_team(
    contest_id: UUID,
    team_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Delete a team from a contest.

    Args:
        contest_id: Contest ID
        team_id: Team ID
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        Success message

    Raises:
        TeamNotFoundError: If team not found or doesn't belong to contest
        PermissionDeniedError: If user not authenticated
    """
    keycloak_user_id = current_user.get("sub")
    if not keycloak_user_id:
        raise PermissionDeniedError("Invalid authentication: missing user ID")

    user_id = (await UserService.get_user_by_keycloak_id(db, keycloak_user_id)).id

    await service.delete_team(team_id, contest_id, user_id)
    logger.info(
        f"Team with ID {team_id} deleted from contest {contest_id} by user {user_id}"
    )

    return MessageResponse(message="Team deleted successfully")


# Team Member Management Routes


@router.post(
    "/{contest_id}/team/{team_id}/members",
    response_model=AddTeamMemberResponse,
    summary="Add member to team",
    dependencies=[can_update("teams")],
)
async def add_member(
    contest_id: UUID,
    team_id: UUID,
    request: AddTeamMemberRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Add a user to a team in a contest.

    Args:
        contest_id: Contest ID
        team_id: Team ID
        request: Request body with user_id to add
        db: Database session
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        Success message with member details

    Raises:
        TeamNotFoundError: If team not found or doesn't belong to contest
        UserNotFoundError: If user not found
        PermissionDeniedError: If user not authenticated
    """
    keycloak_user_id = current_user.get("sub")
    if not keycloak_user_id:
        raise PermissionDeniedError("Invalid authentication: missing user ID")

    current_user_id = (
        await UserService.get_user_by_keycloak_id(db, keycloak_user_id)
    ).id

    return await service.add_member_to_team(
        team_id, request.user_id, contest_id, current_user_id
    )


@router.delete(
    "/{contest_id}/team/{team_id}/members",
    response_model=RemoveTeamMemberResponse,
    summary="Remove member from team",
    dependencies=[can_update("teams")],
)
async def remove_member(
    contest_id: UUID,
    team_id: UUID,
    request: RemoveTeamMemberRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Remove a user from a team in a contest.

    Args:
        contest_id: Contest ID
        team_id: Team ID
        request: Request body with user_id to remove
        db: Database session
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        Success message

    Raises:
        TeamNotFoundError: If team not found or doesn't belong to contest
        UserNotFoundError: If user not found
        PermissionDeniedError: If user not authenticated
    """
    keycloak_user_id = current_user.get("sub")
    if not keycloak_user_id:
        raise PermissionDeniedError("Invalid authentication: missing user ID")

    current_user_id = (
        await UserService.get_user_by_keycloak_id(db, keycloak_user_id)
    ).id

    return await service.remove_member_from_team(
        team_id, request.user_id, contest_id, current_user_id
    )


@router.get(
    "/{contest_id}/team/{team_id}/members",
    response_model=List[UserTeamResponse],
    summary="Get team members",
    dependencies=[can_read("teams")],
)
async def get_team_members(
    contest_id: UUID,
    team_id: UUID,
    service: TeamService = Depends(get_team_service),
):
    """
    Get all members of a team in a contest.

    Args:
        contest_id: Contest ID
        team_id: Team ID
        service: Team service instance

    Returns:
        List of team members

    Raises:
        TeamNotFoundError: If team not found or doesn't belong to contest
    """
    return await service.get_team_members(team_id, contest_id)
