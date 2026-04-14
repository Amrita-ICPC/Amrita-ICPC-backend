"""Student code execution endpoint.

Routes for:
- Running/testing code against test cases
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import can_read, get_current_user_id
from app.core.clients.database import get_db
from app.core.logger import logger
from app.repositories.dto.student.run import StudentCodeRunRequestDTO
from app.schema.student.run import (
    StudentCodeRunRequest,
    StudentCodeRunResponse,
)
from app.service.student.student_run_service import StudentRunService

router = APIRouter(prefix="/contests", tags=["Student - Run"])


def get_student_run_service(db: AsyncSession = Depends(get_db)) -> StudentRunService:
    """Provide StudentRunService instance."""
    return StudentRunService(db)


@router.post(
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
