"""Student contest endpoints.

Routes for:
- Contest discovery and listing
- Contest details and problems
- Contest registration for teams
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import can_read, get_current_user_id
from app.core.clients.database import get_db
from app.core.logger import logger
from app.repositories.contest import ContestRepository
from app.schema.student.contests import (
    StudentContestDetailsResponse,
    StudentContestRegistrationRequest,
    StudentContestRegistrationResponse,
    StudentContestListResponse,
    StudentRegisteredContestListResponse,
    StudentContestProblemsListResponse,
)
from app.service.student.student_contest_service import StudentContestService

router = APIRouter(prefix="/students/contests", tags=["Student - Contests"])


def get_student_contest_service(db: AsyncSession = Depends(get_db)) -> StudentContestService:
    """Provide StudentContestService instance."""
    contest_repo = ContestRepository(db)
    return StudentContestService(contest_repo)


@router.get(
    "",
    response_model=StudentContestListResponse,
    status_code=status.HTTP_200_OK,
    summary="List available contests",
    dependencies=[can_read("contests")],
)
async def get_available_contests(
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
    difficulty: str | None = Query(None, description="Filter by difficulty: EASY, MEDIUM, HARD"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> StudentContestListResponse:
    """
    Get all available public contests.
    
    Optionally filter by difficulty level.
    
    Args:
        user_id: Current authenticated user
        service: StudentContestService instance
        difficulty: Optional difficulty filter
        limit: Pagination limit (1-100)
        offset: Pagination offset
        
    Returns:
        List of available contests with pagination
    """
    if difficulty:
        result = await service.get_contests_by_difficulty(
            user_id=user_id,
            difficulty=difficulty,
            skip=offset,
            limit=limit,
        )
    else:
        result = await service.get_available_contests(
            user_id=user_id,
            skip=offset,
            limit=limit,
        )
    
    logger.info(f"User {user_id} retrieved available contests")
    return result


@router.get(
    "/registered",
    response_model=StudentRegisteredContestListResponse,
    status_code=status.HTTP_200_OK,
    summary="List registered contests",
    dependencies=[can_read("contests")],
)
async def get_registered_contests(
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> StudentRegisteredContestListResponse:
    """
    Get contests student is registered in.
    
    Args:
        user_id: Current authenticated user
        service: StudentContestService instance
        limit: Pagination limit
        offset: Pagination offset
        
    Returns:
        List of registered contests
    """
    result = await service.get_registered_contests(
        user_id=user_id,
        skip=offset,
        limit=limit,
    )
    return result


@router.get(
    "/past",
    response_model=StudentRegisteredContestListResponse,
    status_code=status.HTTP_200_OK,
    summary="List past contests",
    dependencies=[can_read("contests")],
)
async def get_past_contests(
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> StudentRegisteredContestListResponse:
    """
    Get contests that student participated in (finished).
    
    Args:
        user_id: Current authenticated user
        service: StudentContestService instance
        limit: Pagination limit
        offset: Pagination offset
        
    Returns:
        List of past contests
    """
    result = await service.get_past_contests(
        user_id=user_id,
        skip=offset,
        limit=limit,
    )
    return result


@router.get(
    "/{contest_id}",
    response_model=StudentContestDetailsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get contest details",
    dependencies=[can_read("contests")],
)
async def get_contest_details(
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
) -> StudentContestDetailsResponse:
    """
    Get full details of a contest.
    
    Args:
        contest_id: Contest UUID
        user_id: Current authenticated user
        service: StudentContestService instance
        
    Returns:
        Full contest details
    """
    result = await service.get_contest_details(
        user_id=user_id,
        contest_id=contest_id,
    )
    return result


@router.get(
    "/{contest_id}/problems",
    response_model=StudentContestProblemsListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get contest problems",
    dependencies=[can_read("contests")],
)
async def get_contest_problems(
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
):
    """
    Get list of problems in a contest.
    
    Args:
        contest_id: Contest UUID
        user_id: Current authenticated user
        service: StudentContestService instance
        
    Returns:
        List of problems with metadata
    """
    result = await service.get_contest_problems(
        user_id=user_id,
        contest_id=contest_id,
    )
    return result


@router.post(
    "/{contest_id}/register",
    response_model=StudentContestRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register team for contest",
    dependencies=[can_read("contests")],
)
async def register_for_contest(
    contest_id: UUID,
    request: StudentContestRegistrationRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentContestService = Depends(get_student_contest_service),
) -> StudentContestRegistrationResponse:
    """
    Register a team for a contest.
    
    Student must be a member of the team.
    
    Args:
        contest_id: Contest UUID
        request: Registration request with team_id
        user_id: Current authenticated user
        service: StudentContestService instance
        
    Returns:
        Registration confirmation
    """
    result = await service.register_for_contest(
        user_id=user_id,
        contest_id=contest_id,
        team_id=request.team_id,
    )
    logger.info(f"User {user_id} registered team {request.team_id} for contest {contest_id}")
    return result
