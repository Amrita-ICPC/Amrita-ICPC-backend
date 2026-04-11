"""Service for async code execution via Judge0.

This service orchestrates business logic for code execution, using the
Judge0 HTTP client from app.core.clients.judge0 for connection management.

This service focuses on:
- Business logic and orchestration
- Direct API calls to Judge0
- Response transformation and mapping
- Error handling and user-facing exceptions
- Validation against business rules
"""

import asyncio
from typing import Any, Optional

import httpx

from app.core.clients.judge0 import get_judge0_client
from app.core.logger import logger
from app.exceptions.execution import (
    InvalidCodeError,
    InvalidLanguageError,
    InvalidSubmissionTokenError,
)
from app.exceptions.judge0 import Judge0APIError, Judge0ClientError
from app.schema.execution import (
    ExecutionResultResponse,
    Judge0SubmissionResponse,
    Language,
    TokenResponse,
)
from app.validators.execution import ExecutionValidator


class ExecutionService:
    """
    Service orchestrating async code execution via Judge0.

    Delegates low-level HTTP calls to the enterprise Judge0 client in
    app.core.clients.judge0, which handles connection pooling, retries,
    and error recovery.

    This service focuses on:
    - Business logic and orchestration
    - Response transformation and mapping
    - Error handling and user-facing exceptions
    - Future caching and analytics hooks
    """

    async def get_active_languages(self) -> list[Language]:
        """
        Fetch all active programming languages from Judge0.

        Returns:
            List of supported languages

        Raises:
            Judge0ClientError: If Judge0 client fails
        """
        try:
            logger.info("Fetching languages from Judge0")
            client = get_judge0_client()
            response = await client.get("/languages")
            response.raise_for_status()

            languages_data: list[dict[str, Any]] = response.json()
            
            # Map JSON to schema Language objects
            languages = [
                Language(id=lang["id"], name=lang["name"])
                for lang in languages_data
            ]
            
            logger.info(f"Successfully fetched {len(languages)} languages")
            return languages

        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            response_text = exc.response.text
            request_id = exc.response.headers.get("x-request-id")
            logger.error(
                f"Judge0 HTTP error ({status_code}) fetching languages: {response_text}",
                extra={"status_code": status_code, "request_id": request_id},
            )
            detail = response_text or f"HTTP {status_code}"
            raise Judge0APIError(
                status_code=status_code, detail=detail, request_id=request_id
            )
        except httpx.HTTPError as exc:
            logger.error(f"Judge0 connection error fetching languages: {exc}")
            raise Judge0ClientError(f"Failed to fetch languages: {str(exc)}")

    async def submit_code_async(
        self,
        *,
        source_code: str,
        language_id: int,
        stdin: str = "",
        cpu_time_limit: Optional[int] = None,
        memory_limit: Optional[int] = None,
    ) -> TokenResponse:
        """
        Submit source code for asynchronous execution.

        Returns immediately with a submission token. Use check_submission_status()
        to poll for results.

        Args:
            source_code: Source code to execute (max 50KB)
            language_id: Judge0 language ID (e.g., 71 for Python 3)
            stdin: Standard input for the program (optional)
            cpu_time_limit: Custom CPU time limit in seconds (optional)
            memory_limit: Custom memory limit in MB (optional)

        Returns:
            TokenResponse with submission token for polling

        Raises:
            InvalidCodeError: If source code validation fails
            InvalidLanguageError: If language_id validation fails
            Judge0ClientError: If submission to Judge0 fails
        """
        # Input validation
        if len(source_code) > 50000:
            raise InvalidCodeError("Source code exceeds 50KB maximum size limit")

        if not source_code.strip():
            raise InvalidCodeError("Source code cannot be empty")

        if language_id <= 0:
            raise InvalidLanguageError("Invalid language_id: must be positive integer")

        try:
            logger.info(
                "Validating submission request",
                extra={"language_id": language_id, "code_length": len(source_code)},
            )

            # Validate all submission fields against business rules
            ExecutionValidator.validate_submission_request(
                source_code=source_code,
                language_id=language_id,
                stdin=stdin or "",
            )

            logger.info(
                "Submitting code for execution",
                extra={"language_id": language_id, "code_length": len(source_code)},
            )

            # Build submission payload
            payload: dict[str, Any] = {
                "source_code": source_code,
                "language_id": language_id,
                "stdin": stdin or "",
                "base64_encoded": False,
                "wait": False,  # Async: return immediately with token
            }

            # Call Judge0 API directly via client
            client = get_judge0_client()
            response = await client.post(
                "/submissions",
                json=payload,
                params={"base64_encoded": "false", "wait": "false"},
            )
            response.raise_for_status()

            result_data = response.json()
            token = result_data.get("token")
            
            # Guard against missing or invalid token from Judge0
            if not token or not str(token).strip():
                logger.error(
                    "Judge0 submission succeeded but returned invalid token",
                    extra={"token": token, "response": result_data},
                )
                raise Judge0ClientError(
                    "Judge0 returned invalid submission token; cannot track execution"
                )
            
            logger.info(f"Code submitted successfully; token={token}")

            return TokenResponse(token=token)

        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            response_text = exc.response.text
            request_id = exc.response.headers.get("x-request-id")
            logger.error(
                f"Judge0 HTTP error ({status_code}) during submission: {response_text}",
                extra={"status_code": status_code, "request_id": request_id},
            )
            detail = response_text or f"HTTP {status_code}"
            raise Judge0APIError(
                status_code=status_code, detail=detail, request_id=request_id
            )
        except httpx.HTTPError as exc:
            logger.error(f"Judge0 connection error during submission: {exc}")
            raise Judge0ClientError(f"Failed to submit code: {str(exc)}")

    async def check_submission_status(self, token: str) -> ExecutionResultResponse:
        """
        Poll the execution status and results for a submitted code.

        Args:
            token: Submission token from submit_code_async()

        Returns:
            ExecutionResultResponse with execution status and output

        Raises:
            InvalidSubmissionTokenError: If token is invalid
            Judge0ClientError: If status check fails
        """
        # Validate token before status check
        if not token or not token.strip():
            raise InvalidSubmissionTokenError("Submission token cannot be empty")

        try:
            logger.debug(f"Validating and checking submission status; token={token}")

            # Validate token format
            ExecutionValidator.validate_token(token)

            # Call Judge0 API directly via client
            client = get_judge0_client()
            response = await client.get(
                f"/submissions/{token}",
                params={"base64_encoded": "false"},
            )
            response.raise_for_status()

            result_data: dict[str, Any] = response.json()

            # Extract status from nested Judge0 response structure
            status_obj = result_data.get("status", {})
            status_id = status_obj.get("id")
            status_description = status_obj.get("description", "Unknown")

            # Map to response schema
            result = ExecutionResultResponse(
                status_id=status_id,
                status_description=status_description,
                stdout=result_data.get("stdout"),
                stderr=result_data.get("stderr"),
                compile_output=result_data.get("compile_output"),
                time=result_data.get("time"),
                memory=result_data.get("memory"),
            )

            logger.debug(f"Retrieved status: {result.status_description}")

            return result

        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            response_text = exc.response.text
            request_id = exc.response.headers.get("x-request-id")
            logger.error(
                f"Judge0 HTTP error ({status_code}) checking submission status: {response_text}",
                extra={"status_code": status_code, "request_id": request_id},
            )
            detail = response_text or f"HTTP {status_code}"
            raise Judge0APIError(
                status_code=status_code, detail=detail, request_id=request_id
            )
        except httpx.HTTPError as exc:
            logger.error(f"Judge0 connection error checking submission status: {exc}")
            raise Judge0ClientError(
                f"Failed to check submission status: {str(exc)}"
            )

    async def check_batch_submissions(
        self, tokens: list[str]
    ) -> dict[str, ExecutionResultResponse]:
        """
        Batch check status for multiple submissions (more efficient).

        Args:
            tokens: List of submission tokens

        Returns:
            Dictionary mapping token -> ExecutionResultResponse

        Raises:
            InvalidSubmissionTokenError: If tokens are invalid
            Judge0ClientError: If batch check fails
        """
        if not tokens:
            return {}

        try:
            logger.info(f"Validating and batch checking {len(tokens)} submissions")

            # Validate all tokens
            for token in tokens:
                ExecutionValidator.validate_token(token)

            logger.info("Tokens validated; fetching batch results")

            # Fetch all submissions concurrently
            async def fetch_single(token: str) -> tuple[str, ExecutionResultResponse]:
                result = await self.check_submission_status(token)
                return token, result

            tasks = [fetch_single(token) for token in tokens]
            batch_results = await asyncio.gather(*tasks, return_exceptions=False)

            # Convert to dict
            results = {token: result for token, result in batch_results}

            logger.info(f"✓ Batch check completed for {len(results)} submissions")

            return results

        except Judge0ClientError as exc:
            logger.error(f"✗ Batch check failed: {exc}")
            raise


# ============================================================================
# STATUS MAPPING NOTE
# ============================================================================
#
# Judge0 CE API response includes a nested "status" object with both "id" and
# "description" fields. We extract these directly from the response instead of
# maintaining a local status map for consistency with Judge0's API contract.
#
# Example response structure:
# {
#   "status": {
#     "id": 3,
#     "description": "Accepted"
#   },
#   "stdout": "Hello, World!",
#   "stderr": null,
#   ...
# }
