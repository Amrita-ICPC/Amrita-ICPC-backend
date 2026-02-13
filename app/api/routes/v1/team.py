from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    can_update,
    get_current_user,
)
from app.core.clients.database import get_db
from app.core.logger import logger
from app.schema.contest import MessageResponse
from app.schema.team import TeamCreate
from app.service.team_service import TeamService
from app.service.user_service import UserService

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
