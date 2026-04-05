"""
Student API Routes - HTTP endpoints students call.

These are the ACTUAL API endpoints.
Examples:
- GET /api/v1/students/contests
- POST /api/v1/students/contests/{id}/register
- GET /api/v1/students/my-contests
"""

from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user_id
from app.core.clients.database import get_db
from app.core.guards.student import StudentOperationGuard
from app.core.logger import logger
from app.core.response import create_api_response
from app.exceptions.auth import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.repositories.contest import ContestRepository
from app.repositories.student import StudentRepository
from app.repositories.team import TeamRepository
from app.schema.base import APIResponse
from app.schema.student import (
    StudentContestRegistrationRequest,
    StudentContestRegistrationResponse,
    StudentPublicContestResponse,
    StudentRegisteredContestResponse,
)
from app.schema.team import TeamCreate
from app.service.student_service import StudentService
from app.utils.pagination import get_pagination
from app.validators.student import StudentValidator

router = APIRouter(prefix="/students", tags=["Students"])


# ============================================================================
# DEPENDENCY INJECTIONS
# These provide instances to routes
# ============================================================================

def get_student_guard(db: AsyncSession = Depends(get_db)) -> StudentOperationGuard:
    """Provide StudentOperationGuard instance."""
    return StudentOperationGuard(db)


def get_student_repository(db: AsyncSession = Depends(get_db)) -> StudentRepository:
    """Provide StudentRepository instance."""
    return StudentRepository(db)


def get_student_service(
    db: AsyncSession = Depends(get_db),
    student_repo: StudentRepository = Depends(get_student_repository),
) -> StudentService:
    """Provide StudentService instance with all dependencies."""
    contest_repo = ContestRepository(db)
    team_repo = TeamRepository(db)
    guard = StudentOperationGuard(db)
    validator = StudentValidator()
    
    return StudentService(
        student_repository=student_repo,
        contest_repository=contest_repo,
        team_repository=team_repo,
        guard=guard,
        student_validator=validator,
        db=db,
    )


# ============================================================================
# ROUTE 1: GET /students/contests
# Students see list of PUBLIC contests
# ============================================================================

@router.get(
    "/contests",
    response_model=APIResponse[list[StudentPublicContestResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get public contests",
)
async def get_public_contests(
    request: Request,
    user_id: UUID = Depends(get_current_user_id),
    search: str | None = Query(None, description="Search by name"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: StudentService = Depends(get_student_service),
):
    """
    Get all PUBLIC contests.
    
    **What it does:**
    - Returns only contests with is_public=True
    - Filters by search term and status
    - Supports pagination
    
    **Business Rule:**
    - Students CANNOT see private contests
    
    **Example request:**
    GET /api/v1/students/contests?search=ICPC&status=SCHEDULED&page=1&page_size=10
    
    **Example response:**
    {
        "success": true,
        "data": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "ICPC Regionals 2026",
                "is_registered": false
            }
        ],
        "message": "Retrieved 10 public contests",
        "meta": {
            "pagination": {
                "total": 25,
                "page": 1,
                "page_size": 10
            }
        }
    }
    """
    try:
        skip = (page - 1) * page_size

        # Call SERVICE to get contests
        total, contests = await service.get_public_contests(
            search_term=search,
            status=status_filter,
            skip=skip,
            limit=page_size,
        )

        pagination = get_pagination(total=total, page=page, page_size=page_size)

        logger.info(f"Student {user_id} retrieved {len(contests)} public contests")

        return create_api_response(
            request,
            data=contests,
            message=f"Retrieved {len(contests)} public contests",
            pagination=pagination,
        )

    except Exception as e:
        logger.error(f"Error getting public contests: {str(e)}")
        raise


# ============================================================================
# ROUTE 2: GET /students/contests/{contest_id}
# Students see details of ONE PUBLIC contest
# ============================================================================

@router.get(
    "/contests/{contest_id}",
    response_model=APIResponse[StudentPublicContestResponse],
    status_code=status.HTTP_200_OK,
    summary="Get contest details",
)
async def get_public_contest(
    request: Request,
    contest_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentService = Depends(get_student_service),
):
    """
    Get details of ONE PUBLIC contest.
    
    **Business Rules:**
    - Contest must be is_public=True
    - Returns 404 if private (security through obscurity)
    
    **Example request:**
    GET /api/v1/students/contests/550e8400-e29b-41d4-a716-446655440000
    
    **Example response:**
    {
        "success": true,
        "data": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "ICPC Regionals 2026",
            "status": "SCHEDULED",
            "start_time": "2026-05-15T09:00:00Z"
        }
    }
    """
    try:
        contest = await service.get_public_contest_by_id(contest_id)
        
        logger.info(f"Student {user_id} viewed contest {contest_id}")

        return create_api_response(
            request,
            data=contest,
            message="Contest details retrieved successfully",
        )

    except ContestNotFoundError:
        logger.warning(f"Contest not found: {contest_id}")
        raise
    except Exception as e:
        logger.error(f"Error getting contest: {str(e)}")
        raise


# ============================================================================
# ROUTE 3: POST /students/contests/{contest_id}/register
# Student registers in a contest by creating a team
# ============================================================================

@router.post(
    "/contests/{contest_id}/register",
    response_model=APIResponse[StudentContestRegistrationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register in contest",
)
async def register_in_contest(
    request: Request,
    contest_id: UUID,
    registration_data: StudentContestRegistrationRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentService = Depends(get_student_service),
):
    """
    Register student in a PUBLIC contest.
    
    **What it does:**
    1. Check contest is public
    2. Check contest allows registration
    3. Check student hasn't registered yet
    4. Create team
    5. Register team in contest
    
    **Business Rules:**
    - Contest must be PUBLIC
    - Contest must be SCHEDULED or RUNNING
    - Student can't be in 2+ teams for same contest
    - Team must have 1-3 members
    
    **Example request:**
    POST /api/v1/students/contests/550e8400-e29b-41d4-a716-446655440000/register
    {
        "team_name": "Alpha Squad",
        "team_description": "Our competitive team",
        "member_emails": ["john@amrita.edu", "jane@amrita.edu"]
    }
    
    **Example response (SUCCESS):**
    {
        "success": true,
        "data": {
            "team_id": "650e8400-e29b-41d4-a716-446655440000",
            "team_name": "Alpha Squad",
            "contest_id": "550e8400-e29b-41d4-a716-446655440000",
            "contest_name": "ICPC Regionals 2026",
            "registration_date": "2026-04-06T10:30:00Z"
        },
        "message": "Successfully registered in contest with team 'Alpha Squad'"
    }
    
    **Example response (FAILURE - Already registered):**
    {
        "success": false,
        "error": "You are already registered in this contest",
        "status_code": 400
    }
    """
    try:
        # Convert request to TeamCreate schema
        team_create = TeamCreate(
            name=registration_data.team_name,
            description=registration_data.team_description,
            members=registration_data.member_emails,
        )

        # Call SERVICE to register
        response = await service.register_in_contest(
            student_id=user_id,
            contest_id=contest_id,
            team_data=team_create,
        )

        logger.info(f"Student {user_id} registered in contest {contest_id}")

        return create_api_response(
            request,
            data=response,
            message=f"Successfully registered with team '{response.team_name}'",
            status_code=status.HTTP_201_CREATED,
        )

    except PermissionDeniedError as e:
        logger.warning(f"Registration denied: {str(e)}")
        raise
    except ContestNotFoundError as e:
        logger.warning(f"Contest not found: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error registering: {str(e)}")
        raise


# ============================================================================
# ROUTE 4: GET /students/my-contests
# Student sees contests they're registered in
# ============================================================================

@router.get(
    "/my-contests",
    response_model=APIResponse[list[StudentRegisteredContestResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get my registered contests",
)
async def get_my_registered_contests(
    request: Request,
    user_id: UUID = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: StudentService = Depends(get_student_service),
):
    """
    Get contests where STUDENT is registered.
    
    **What it does:**
    - Finds all teams student is in
    - Gets contests for those teams
    - Shows team + team_status for each
    
    **Business Rules:**
    - Student can see BOTH public and private contests
    - But only ones they're registered in
    
    **Example request:**
    GET /api/v1/students/my-contests?page=1&page_size=10
    
    **Example response:**
    {
        "success": true,
        "data": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "ICPC Regionals 2026",
                "team_id": "650e8400-e29b-41d4-a716-446655440000",
                "team_name": "Alpha Squad",
                "team_status": "SUBMITTED"
            }
        ]
    }
    """
    try:
        skip = (page - 1) * page_size

        # Call SERVICE to get contests
        total, contests = await service.get_my_registered_contests(
            student_id=user_id,
            skip=skip,
            limit=page_size,
        )

        pagination = get_pagination(total=total, page=page, page_size=page_size)

        logger.info(f"Student {user_id} retrieved {len(contests)} registered contests")

        return create_api_response(
            request,
            data=contests,
            message=f"Retrieved {len(contests)} registered contests",
            pagination=pagination,
        )

    except Exception as e:
        logger.error(f"Error getting registered contests: {str(e)}")
        raise