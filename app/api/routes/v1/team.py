from typing import Any, Dict, List
from uuid import UUID

from fastapi import FastAPI, Depends, Query, status, APIRouter
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AccessControl,
    can_create,
    can_delete,
    can_read,
    can_update,
    get_current_user
)

from app.core.clients.database import get_db
from app.core.logger import logger
from app.exceptions.auth import PermissionDeniedError
from app.schema.team import (
    TeamCreate,
    TeamUpdate,
    TeamResponse,
    AddTeamMemberRequest,
    AddTeamMemberResponse,
    UserTeamResponse,
    RemoveTeamMemberRequest,
    RemoveTeamMemberResponse,
    MessageResponse
)

from app.service.team_service import TeamService
from app.service.user_service import UserService

router = APIRouter()

def get_team_service(db: Session = Depends(get_db)) -> TeamService:
    return TeamService(db)

@router.post(
    "/",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="create a new team",
    dependencies=[can_create("teams")]
)
async def create_team(
    team: TeamCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service)
):
    """
    Create a new team.

    Args:
        team: Team creation data
        db: Database session
        current_user: Current authenticated user
        service: Team service instance

    Returns:
        Success message
    """
    keycloak_user_id = current_user["sub"]
    db_user = UserService.get_user_by_keycloak_id(db, keycloak_user_id)
    created_team = await service.create_team(team)
    logger.info(
        f"Team '{created_team.name}' with ID {created_team.id} created by user {db_user.id}"
    )

    return MessageResponse(message="Team created successfully")


@router.get(
    "/my-teams",
    response_model=Dict[str, Any],
    summary="Get current user's teams",
    dependencies=[can_read("teams")],
)
async def get_my_teams(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(100, ge=1, le=100, description="Limit for pagination"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Get all teams for the current user.

    Args:
        skip: Offset for pagination
        limit: Limit for pagination
        service: Team service instance
        current_user: Current authenticated user

    Returns:
        Paginated list of teams
    """
    keycloak_user_id = current_user["sub"]
    db_user = UserService.get_user_by_keycloak_id(db, keycloak_user_id)
    total, teams = await service.get_user_teams(db_user.id, skip, limit)
    return {"total": total, "teams": teams}


@router.get(
    "/{team_id}",
    response_model=TeamResponse,
    summary="Get Team by ID",
    dependencies=[can_read("teams")],
)
async def get_team(
    team_id: UUID,
    service: TeamService = Depends(get_team_service)
):
    """
    Get a specific team by its ID.

    Args:
        team_id: Team ID
        service: Team service instance

    Returns:
        Team details
    """
    return await service.get_team_by_id(team_id)

@router.patch(
    "/{team_id}",
    response_model=MessageResponse,
    summary="Update team",
    dependencies=[can_update("teams")]
)
async def update_team(
    team_id: UUID,
    team_data: TeamUpdate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Partially update an existing team.

    Args:
        team_id: Team ID
        team_data: Team update data
        service: Team service instance

    Returns:
        Success message
    """
    kc_id = current_user.get("sub")
    user_id = UserService.get_user_by_keycloak_id(db, kc_id).id
    await service.update_team(team_id, team_data)

    logger.info(f"Team with ID {team_id} updated by user {user_id}")
    return MessageResponse(message="Team updated successfully")


@router.delete(
    "/{team_id}",
    response_model=MessageResponse,
    summary="Delete team",
    dependencies=[can_delete("teams")]
)
async def delete_team(
    team_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: TeamService = Depends(get_team_service),
):
    """
    Delete a team by its ID.

    Args:
        team_id: Team ID
        service: Team service instance

    Returns:
        Success message
    """
    kc_id = current_user.get("sub")
    user_id = UserService.get_user_by_keycloak_id(db, kc_id).id
    
    await service.delete_team(team_id)
    
    logger.info(f"Team with ID {team_id} deleted by user {user_id}")
    return MessageResponse(message="Team deleted successfully")

@router.post(
    "/{team_id}/members/{user_id}",
    response_model=AddTeamMemberResponse,
    summary="Add member to team",
    dependencies=[can_update("teams")],
)
async def add_member(
    team_id: UUID,
    user_id: UUID,
    service: TeamService = Depends(get_team_service),
):
    """
    Add a user to the team.
    """
    return await service.add_member_to_team(team_id, user_id)

@router.delete(
    "/{team_id}/members/{user_id}",
    response_model=RemoveTeamMemberResponse,
    summary="Remove member from team",
    dependencies=[can_update("teams")],
)
async def remove_member(
    team_id: UUID,
    user_id: UUID,
    service: TeamService = Depends(get_team_service),
):
    """
    Remove a user from the team.
    """
    return await service.remove_member_from_team(team_id, user_id)

@router.get(
    "/{team_id}/members",
    response_model=List[UserTeamResponse],
    summary="Get team members",
    dependencies=[can_read("teams")],
)
async def get_team_members(
    team_id: UUID,
    service: TeamService = Depends(get_team_service),
):
    """
    Get all members of a team.
    """
    return await service.get_team_members(team_id)

