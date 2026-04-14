"""Student team endpoints.

Routes for:
- Team management (create, join, leave)
- Team listing and details
- Team membership operations (add/remove members)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import can_read, get_current_user_id
from app.core.clients.database import get_db
from app.core.logger import logger
from app.repositories.team import TeamRepository
from app.schema.student.teams import (
    StudentTeamCreateRequest,
    StudentTeamCreateAndJoinResponse,
    StudentTeamJoinRequest,
    StudentTeamJoinResponse,
    StudentTeamListResponse,
    StudentTeamResponse,
    StudentTeamAddMemberRequest,
    StudentTeamAddMemberResponse,
    StudentTeamRemoveMemberRequest,
    StudentLeaveTeamResponse,
)
from app.service.student.student_team_service import StudentTeamService

router = APIRouter(prefix="/students/teams", tags=["Student - Teams"])


def get_student_team_service(db: AsyncSession = Depends(get_db)) -> StudentTeamService:
    """Provide StudentTeamService instance."""
    team_repo = TeamRepository(db)
    return StudentTeamService(team_repo)


@router.get(
    "",
    response_model=StudentTeamListResponse,
    status_code=status.HTTP_200_OK,
    summary="List my teams",
    dependencies=[can_read("contests")],
)
async def get_my_teams(
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> StudentTeamListResponse:
    """
    Get all teams student is a member of.
    
    Args:
        user_id: Current authenticated user
        service: StudentTeamService instance
        limit: Pagination limit
        offset: Pagination offset
        
    Returns:
        List of teams
    """
    result = await service.get_my_teams(
        user_id=user_id,
        skip=offset,
        limit=limit,
    )
    return result


@router.get(
    "/{team_id}",
    response_model=StudentTeamResponse,
    status_code=status.HTTP_200_OK,
    summary="Get team details",
    dependencies=[can_read("contests")],
)
async def get_team_details(
    team_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> StudentTeamResponse:
    """
    Get team details including members.
    
    Args:
        team_id: Team UUID
        user_id: Current authenticated user
        service: StudentTeamService instance
        
    Returns:
        Team details with member list
    """
    result = await service.get_team_by_id(
        user_id=user_id,
        team_id=team_id,
    )
    return result


@router.get(
    "/contests/{contest_id}/available",
    response_model=StudentTeamListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get available teams to join",
    dependencies=[can_read("contests")],
)
async def get_available_teams(
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> StudentTeamListResponse:
    """
    Get teams available to join in a contest.
    
    Teams must have available slots.
    
    Args:
        contest_id: Contest UUID
        user_id: Current authenticated user
        service: StudentTeamService instance
        limit: Pagination limit
        offset: Pagination offset
        
    Returns:
        List of available teams
    """
    result = await service.get_available_teams_in_contest(
        user_id=user_id,
        contest_id=contest_id,
        skip=offset,
        limit=limit,
    )
    return result


@router.post(
    "",
    response_model=StudentTeamCreateAndJoinResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and join team",
    dependencies=[can_read("contests")],
)
async def create_and_join_team(
    request: StudentTeamCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> StudentTeamCreateAndJoinResponse:
    """
    Create a new team and join it.
    
    Only for public contests.
    
    Args:
        request: Team creation request
        user_id: Current authenticated user
        service: StudentTeamService instance
        
    Returns:
        Created team details
    """
    result = await service.create_and_join_team(
        contest_id=request.contest_id,
        team_data=request,
        created_by=user_id,
    )
    logger.info(f"User {user_id} created team {request.name}")
    return result


@router.post(
    "/{team_id}/join",
    response_model=StudentTeamJoinResponse,
    status_code=status.HTTP_200_OK,
    summary="Join existing team",
    dependencies=[can_read("contests")],
)
async def join_team(
    team_id: UUID,
    request: StudentTeamJoinRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> StudentTeamJoinResponse:
    """
    Join an existing team.
    
    Args:
        team_id: Team UUID to join
        request: Join request
        user_id: Current authenticated user
        service: StudentTeamService instance
        
    Returns:
        Join confirmation
    """
    result = await service.join_team(
        team_id=team_id,
        contest_id=request.contest_id,
        user_id=user_id,
    )
    logger.info(f"User {user_id} joined team {team_id}")
    return result


@router.post(
    "/{team_id}/leave",
    response_model=StudentLeaveTeamResponse,
    status_code=status.HTTP_200_OK,
    summary="Leave team",
    dependencies=[can_read("contests")],
)
async def leave_team(
    team_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> StudentLeaveTeamResponse:
    """
    Leave a team.
    
    Args:
        team_id: Team UUID to leave
        user_id: Current authenticated user
        service: StudentTeamService instance
        
    Returns:
        Leave confirmation
    """
    result = await service.leave_team(
        user_id=user_id,
        team_id=team_id,
    )
    logger.info(f"User {user_id} left team {team_id}")
    return result


@router.post(
    "/{team_id}/members",
    response_model=StudentTeamAddMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add member to team (leader only)",
    dependencies=[can_read("contests")],
)
async def add_member_to_team(
    team_id: UUID,
    request: StudentTeamAddMemberRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> StudentTeamAddMemberResponse:
    """
    Add a member to team (leader only).
    
    Args:
        team_id: Team UUID
        request: Add member request with user_id
        user_id: Current authenticated user (must be leader)
        service: StudentTeamService instance
        
    Returns:
        Addition confirmation
    """
    result = await service.add_member_to_team(
        team_id=team_id,
        leader_user_id=user_id,
        member_email=request.member_email,
    )
    logger.info(f"User {user_id} added member {request.member_email} to team {team_id}")
    return result


@router.delete(
    "/{team_id}/members/{member_id}",
    response_model=StudentLeaveTeamResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove member from team (leader only)",
    dependencies=[can_read("contests")],
)
async def remove_member_from_team(
    team_id: UUID,
    member_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> StudentLeaveTeamResponse:
    """
    Remove a member from team (leader only).
    
    Args:
        team_id: Team UUID
        member_id: Member UUID to remove
        user_id: Current authenticated user (must be leader)
        service: StudentTeamService instance
        
    Returns:
        Removal confirmation
    """
    result = await service.remove_member_from_team(
        team_id=team_id,
        leader_user_id=user_id,
        member_user_id=member_id,
    )
    logger.info(f"User {user_id} removed member {member_id} from team {team_id}")
    return result
