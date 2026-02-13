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
from app.core.logger import logger
from app.schema.contest import MessageResponse
from app.schema.team import (
    ContestTeamResponse,
    TeamCreate,
    TeamListResponse,
)
from app.service.team_service import TeamService
from app.service.user_service import UserService
from app.utils.enums import TeamStatus

router = APIRouter()


def get_team_service(db: Session = Depends(get_db)) -> TeamService:
    return TeamService(db)


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
    user_id = (await UserService.get_user_by_keycloak_id(service.db, kc_id)).id
    skip = (page - 1) * page_size
    total, teams = await service.get_contest_teams(
        contest_id, user_id, search, status, skip, page_size
    )
    return TeamListResponse(total=total, teams=teams)


@router.get(
    "/contests/{contest_id}/teams/{team_id}",
    response_model=ContestTeamResponse,
    summary="Get team by ID",
    dependencies=[can_read("contests")],
)
async def get_team(
    contest_id: UUID,
    team_id: UUID,
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
    user_id = (await UserService.get_user_by_keycloak_id(service.db, kc_id)).id
    return await service.get_team_by_id(contest_id, team_id, user_id)
