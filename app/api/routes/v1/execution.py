"""API routes for code execution via Judge0."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.core.logger import logger
from app.exceptions.judge0 import Judge0ClientError
from app.schema.execution import (
    CodeRunAsyncRequest,
    ExecutionResultResponse,
    Language,
    TokenResponse,
)
from app.service.execution_service import ExecutionService

router = APIRouter(prefix="/execution", tags=["execution"])


def get_execution_service() -> ExecutionService:
    """Dependency: Provide ExecutionService instance."""
    return ExecutionService()


@router.get(
    "/languages",
    response_model=list[Language],
    summary="Get supported programming languages",
    description="Fetch all active programming languages supported by Judge0",
    responses={
        502: {"description": "Judge0 service unavailable"},
    },
)
async def get_languages(
    service: ExecutionService = Depends(get_execution_service),
) -> list[Language]:
    """
    Retrieve all supported programming languages from Judge0.

    Returns:
        List of available languages with id and name

    Raises:
        HTTPException: 502 if Judge0 is unreachable
    """
    try:
        languages = await service.get_active_languages()
        logger.info(f"Returned {len(languages)} languages to client")
        return languages

    except Judge0ClientError as exc:
        logger.error(f"Failed to fetch languages: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Judge0 service unavailable. Unable to fetch languages.",
        )


@router.post(
    "/run-async",
    response_model=TokenResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit code for async execution",
    description="Submit source code and receive a token for polling results",
    responses={
        202: {"description": "Code submitted successfully; use token to poll"},
        400: {"description": "Invalid request (code too large, missing fields)"},
        502: {"description": "Judge0 service unavailable"},
    },
)
async def run_code_async(
    request: CodeRunAsyncRequest,
    service: ExecutionService = Depends(get_execution_service),
) -> TokenResponse:
    """
    Submit source code for asynchronous execution.

    Accepts source code and returns immediately with a token.
    Use the /execution/result/{token} endpoint to poll for results.

    Args:
        request: Code submission details (source_code, language_id, stdin)
        service: ExecutionService instance

    Returns:
        TokenResponse (HTTP 202) containing submission token

    Raises:
        HTTPException: 400 if input is invalid, 502 if Judge0 fails
    """
    try:
        # Pydantic validation ensures source_code, language_id are valid
        logger.info(
            f"Code submission received",
            extra={
                "language_id": request.language_id,
                "code_size": len(request.source_code),
            },
        )

        token_response = await service.submit_code_async(
            source_code=request.source_code,
            language_id=request.language_id,
            stdin=request.stdin or "",
        )

        logger.info(f"Submission successful; token={token_response.token}")

        return token_response

    except ValueError as exc:
        logger.warning(f"Invalid submission request: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    except Judge0ClientError as exc:
        logger.error(f"Judge0 submission failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to submit code to Judge0. Service may be temporarily unavailable.",
        )


@router.get(
    "/result/{token}",
    response_model=ExecutionResultResponse,
    summary="Get execution result",
    description="Poll execution status and results for submitted code",
    responses={
        200: {"description": "Execution result retrieved"},
        400: {"description": "Invalid token"},
        502: {"description": "Judge0 service unavailable"},
    },
)
async def get_execution_result(
    token: str,
    service: ExecutionService = Depends(get_execution_service),
) -> ExecutionResultResponse:
    """
    Retrieve the execution status and results for submitted code.

    Status codes:
    - 1: In Queue - waiting for execution
    - 2: Processing - currently executing
    - 3: Accepted (AC) - all tests passed
    - 4: Wrong Answer (WA) - output mismatch
    - 5: Time Limit Exceeded (TLE) - execution too slow
    - 6: Compilation Error (CE) - failed to compile
    - 7: Runtime Error (RE) - crashed during execution

    Args:
        token: Submission token from /execution/run-async
        service: ExecutionService instance

    Returns:
        ExecutionResultResponse with status and output details

    Raises:
        HTTPException: 400 if token is invalid, 502 if Judge0 fails
    """
    try:
        logger.debug(f"Status poll received; token={token[:10]}...")

        result = await service.check_submission_status(token)

        logger.debug(
            f"Returned result to client",
            extra={"status": result.status_description},
        )

        return result

    except ValueError as exc:
        logger.warning(f"Invalid status request: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    except Judge0ClientError as exc:
        logger.error(f"Judge0 status check failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve execution result from Judge0.",
        )


@router.get(
    "/batch-results",
    response_model=dict[str, ExecutionResultResponse],
    summary="Batch check multiple submissions",
    description="Poll results for multiple submissions in a single request",
    responses={
        200: {"description": "Results for all requested tokens"},
        400: {"description": "Invalid tokens"},
        502: {"description": "Judge0 service unavailable"},
    },
)
async def batch_get_results(
    tokens: list[str] = None,
    service: ExecutionService = Depends(get_execution_service),
) -> dict[str, ExecutionResultResponse]:
    """
    Batch fetch results for multiple submissions (more efficient than individual polls).

    Args:
        tokens: Query parameter list of submission tokens
        service: ExecutionService instance

    Returns:
        Dictionary mapping token -> ExecutionResultResponse

    Raises:
        HTTPException: 400 if tokens invalid, 502 if Judge0 fails
    """
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one token must be provided",
        )

    try:
        logger.info(f"Batch results request for {len(tokens)} submissions")

        results = await service.check_batch_submissions(tokens)

        logger.info(f"Batch results returned; count={len(results)}")

        return results

    except ValueError as exc:
        logger.warning(f"Invalid batch request: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    except Judge0ClientError as exc:
        logger.error(f"Batch check failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve batch results from Judge0.",
        )
