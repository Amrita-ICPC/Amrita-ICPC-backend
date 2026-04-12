"""API routes for code execution via Judge0."""

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import can_read
from app.core.clients.database import get_db
from app.core.logger import logger
from app.exceptions.execution import CompilationError, NoTestCasesError
from app.exceptions.judge0 import Judge0ClientError
from app.schema.execution import (
    CodeRunRequest,
    CodeRunResponse,
)
from app.service.code_execution_service import CodeExecutionService

router = APIRouter(prefix="/execution", tags=["execution"])


def get_code_execution_service(db: AsyncSession = Depends(get_db)) -> CodeExecutionService:
    """Dependency: Provide CodeExecutionService instance for practice runs."""
    return CodeExecutionService(db)


@router.post(
    "/run",
    response_model=CodeRunResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[can_read("questions")],
    summary="Run code against test cases (practice mode)",
    description="Execute code against all non-hidden test cases and get immediate feedback",
    responses={
        200: {"description": "Code executed successfully; see results"},
        400: {"description": "Question not found or no test cases available"},
        422: {"description": "Invalid request (code too large, missing fields)"},
        502: {"description": "Judge0 service unavailable"},
    },
)
async def run_code(
    request: CodeRunRequest,
    db: AsyncSession = Depends(get_db),
    service: CodeExecutionService = Depends(get_code_execution_service),
) -> CodeRunResponse:
    """
    Execute code against all non-hidden test cases in practice mode.

    Runs submitted code immediately against visible test cases and returns results.
    No submission record is created; results are ephemeral feedback only.

    Flow:
    1. Validate question exists
    2. Fetch non-hidden test cases
    3. Submit code to Judge0 for each test case (parallel)
    4. Check compilation on first test case (early exit if error)
    5. Batch poll remaining results efficiently
    6. Return detailed per-test-case results

    Args:
        request: CodeRunRequest with question_id, source_code, language_id
        db: Database session for question/testcase lookups
        service: CodeExecutionService instance

    Returns:
        CodeRunResponse (HTTP 200) with:
        - testcases: list of execution results per test case
        - total: number of test cases executed
        - passed: number of test cases that passed

    Raises:
        HTTPException: 400 if question not found or no test cases
        HTTPException: 422 if request validation fails
        HTTPException: 502 if Judge0 service fails
    """
    try:
        logger.info(
            f"Code run initiated",
            extra={
                "question_id": request.question_id,
                "language_id": request.language_id,
                "code_size": len(request.source_code),
            },
        )

        # Execute code against non-hidden test cases
        result = await service.run_code(
            question_id=request.question_id,
            source_code=request.source_code,
            language_id=request.language_id,
        )

        logger.info(
            f"Code run completed successfully",
            extra={
                "question_id": request.question_id,
                "total": result.total,
                "passed": result.passed,
            },
        )

        return result

    except NoTestCasesError as exc:
        logger.warning(f"No test cases available: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    # CompilationError will be handled by exception_handler in errors.py

    except Judge0ClientError as exc:
        logger.error(f"Judge0 service error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to execute code on Judge0. Service may be temporarily unavailable.",
        ) from exc

