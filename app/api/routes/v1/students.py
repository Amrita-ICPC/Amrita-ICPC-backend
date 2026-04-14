"""API routes for all student endpoints.

Complete API surface for:
- Contest discovery, registration, and participation
- Team management and membership
- Code execution and testing
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import can_read, get_current_user_id
from app.core.clients.database import get_db
from app.core.logger import logger
from app.repositories.dto.student.run import StudentCodeRunRequestDTO
from app.schema.student.contests import (
    StudentContestDetailsResponse,
    StudentContestRegistrationRequest,
    StudentContestRegistrationResponse,
    StudentContestListResponse,
    StudentRegisteredContestListResponse,
    StudentContestProblemsListResponse,
)
from app.schema.student.run import (
    StudentCodeRunRequest,
    StudentCodeRunResponse,
)
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
from app.service.student.student_contest_service import StudentContestService
from app.service.student.student_run_service import StudentRunService
from app.service.student.student_team_service import StudentTeamService

# Create routers for different resource groups
contests_router = APIRouter(prefix="/students/contests", tags=["Student - Contests"])
teams_router = APIRouter(prefix="/students/teams", tags=["Student - Teams"])
run_router = APIRouter(prefix="/contests", tags=["Student - Run"])


# ============================================================================
# DEPENDENCIES
# ============================================================================

def get_student_contest_service(db: AsyncSession = Depends(get_db)) -> StudentContestService:
    """Provide StudentContestService instance."""
    return StudentContestService(db)


def get_student_team_service(db: AsyncSession = Depends(get_db)) -> StudentTeamService:
    """Provide StudentTeamService instance."""
    return StudentTeamService(db)


def get_student_run_service(db: AsyncSession = Depends(get_db)) -> StudentRunService:
    """Provide StudentRunService instance."""
    return StudentRunService(db)


# ============================================================================
# CONTEST ENDPOINTS
# ============================================================================

@contests_router.get(
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


@contests_router.get(
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


@contests_router.get(
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


@contests_router.get(
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


@contests_router.get(
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


@contests_router.post(
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


@contests_router.post(
    "/{contest_id}/teams",
    response_model=StudentTeamCreateAndJoinResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and join team",
    dependencies=[can_read("contests")],
)
async def create_and_join_team(
    contest_id: UUID,
    request: StudentTeamCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> StudentTeamCreateAndJoinResponse:
    """
    Create a new team and join it for a contest.
    
    Only for public contests.
    
    Args:
        contest_id: Contest UUID from path
        request: Team creation request with name, description, contest_id
        user_id: Current authenticated user
        service: StudentTeamService instance
        
    Returns:
        Created team details
    """
    result = await service.create_and_join_team(
        user_id=user_id,
        team_name=request.name,
        contest_id=request.contest_id,
    )
    logger.info(f"User {user_id} created team {request.name}")
    return result


# ============================================================================
# TEAM ENDPOINTS
# ============================================================================

@teams_router.get(
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


@teams_router.get(
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


@teams_router.get(
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


@teams_router.post(
    "/contests/{contest_id}",
    response_model=StudentTeamCreateAndJoinResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and join team",
    dependencies=[can_read("contests")],
)
async def create_and_join_team(
    contest_id: UUID,
    request: StudentTeamCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> StudentTeamCreateAndJoinResponse:
    """
    Create a new team and join it.
    
    Only for public contests.
    
    Args:
        contest_id: Contest UUID from path
        request: Team creation request
        user_id: Current authenticated user
        service: StudentTeamService instance
        
    Returns:
        Created team details
    """
    result = await service.create_and_join_team(
        user_id=user_id,
        team_name=request.name,
        contest_id=contest_id,
    )
    logger.info(f"User {user_id} created team {request.name}")
    return result


@teams_router.post(
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
        user_id=user_id,
        team_id=team_id,
    )
    logger.info(f"User {user_id} joined team {team_id}")
    return result


@teams_router.post(
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


@teams_router.post(
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
        user_id=user_id,
        team_id=team_id,
        new_member_id=request.user_id,
    )
    logger.info(f"User {user_id} added member {request.user_id} to team {team_id}")
    return result


@teams_router.delete(
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
        user_id=user_id,
        team_id=team_id,
        member_to_remove=member_id,
    )
    logger.info(f"User {user_id} removed member {member_id} from team {team_id}")
    return result


# ============================================================================
# RUN ENDPOINT (Code Execution)
# ============================================================================

@run_router.post(
    "/{contest_id}/questions/{question_id}/run",
    response_model=StudentCodeRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Test code against a test case",
    description="Run student code against a single test case for immediate feedback",
    dependencies=[can_read("contests")],
    responses={
        200: {"description": "Code executed - see result details"},
        403: {"description": "Student not in contest"},
        404: {"description": "Contest, question, or test case not found"},
        422: {"description": "Invalid request"},
    },
)
async def run_student_code(
    contest_id: UUID,
    question_id: UUID,
    code_request: StudentCodeRunRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentRunService = Depends(get_student_run_service),
) -> StudentCodeRunResponse:
    """
    Test run code against a single test case.
    
    Student submits code to quickly test against one test case before official submission.
    Result is NOT stored in database - only ephemeral feedback for testing.
    
    Flow:
    1. Verify student is in contest (via team registration)
    2. Verify question exists in contest
    3. Get test case (use first if not specified)
    4. Execute code via Judge0
    5. Return detailed result with verdict
    
    Args:
        contest_id: Contest UUID from URL path
        question_id: Question UUID from URL path
        code_request: StudentCodeRunRequest with code, language_id, optional testcase_id
        user_id: Current authenticated user UUID
        service: StudentRunService instance
        
    Returns:
        StudentCodeRunResponse: Execution result with verdict and output
        
    Raises:
        PermissionDeniedError: If student not in contest
        ContestNotFoundError: If contest not found
        QuestionNotFoundError: If question not found or not in contest
    """
    # Build request DTO
    run_request = StudentCodeRunRequestDTO(
        user_id=user_id,
        contest_id=contest_id,
        question_id=question_id,
        code=code_request.code,
        language_id=code_request.language_id,
        testcase_id=code_request.testcase_id,
    )
    
    # Execute code
    result = await service.run_code(run_request)
    
    logger.info(
        f"Code run for user {user_id} on question {question_id} in contest {contest_id}: "
        f"verdict={result.result.status_description}"
    )
    
    return result


# ============================================================================
# ROUTER EXPORTS
# ============================================================================

# Combine all student routers into a single module router
router = APIRouter()
router.include_router(contests_router)
router.include_router(teams_router)
router.include_router(run_router)
