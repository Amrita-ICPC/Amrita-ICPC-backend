"""Judge0 Repository for code execution operations.

This repository encapsulates all Judge0 API interactions for both "run" (practice)
and "submit" (final) code execution workflows. Common features are centralized here
and reused by service layer implementations.

These operations are NOT persisted in the database (runs are ephemeral).
Only submissions are persisted, handled at the service layer.
"""

import asyncio
from typing import Optional

import httpx

from app.core.clients.judge0 import Judge0StatusCode, get_judge0_client
from app.core.logger import logger
from app.exceptions.judge0 import (
    Judge0APIError,
    Judge0ClientError,
    Judge0ConnectionError,
    Judge0ServiceUnavailableError,
    Judge0TimeoutError,
)
from app.repositories.dto.judge0 import (
    Judge0ExecutionRequestDTO,
    Judge0ExecutionResultDTO,
    Judge0SubmissionDTO,
)


class Judge0Repository:
    """Repository for Judge0 code execution operations.

    Encapsulates all async interactions with Judge0 API:
    - Submitting code for execution
    - Polling for execution results
    - Handling timeouts and retries
    - Error handling and mapping

    Reusable for both "run" (practice, ephemeral) and "submit" (final, persisted) workflows.
    """

    # Constants for polling behavior
    POLL_INTERVAL_MS = 500  # Wait 500ms between polls
    MAX_POLL_ATTEMPTS = 120  # Max 60 seconds (120 * 500ms)
    BATCH_POLL_SIZE = 20  # Poll up to 20 submissions in one batch request

    def __init__(self):
        """Initialize Judge0 repository."""
        pass

    async def submit_code(
        self, request: Judge0ExecutionRequestDTO, stdin: str
    ) -> Judge0SubmissionDTO:
        """Submit source code to Judge0 for execution with stdin.

        Submits code immediately without waiting for execution completion.
        Use `wait_for_completion()` to poll results.

        Args:
            request: Execution request with source code, language ID, question ID
            stdin: Standard input for the program (from TestCase.input)

        Returns:
            Judge0SubmissionDTO with submission token and initial status

        Raises:
            Judge0ClientError: If submission fails
            Judge0ConnectionError: If connection to Judge0 fails
            Judge0TimeoutError: If request times out
        """
        client = get_judge0_client()

        try:
            payload = {
                "source_code": request.source_code,
                "language_id": request.language_id,
                "stdin": stdin,
            }

            # Submit to Judge0
            response = await client.post(
                "/submissions",
                json=payload,
                params={"base64_encoded": "false", "wait": "false"},
            )

            if response.status_code != 201:
                await self._handle_api_error(response)

            data = response.json()
            token = data.get("token")

            if not token:
                raise Judge0APIError(
                    status_code=response.status_code,
                    detail="Judge0 API returned submission without token",
                    request_id=response.headers.get("X-Request-ID"),
                )

            logger.debug(f"Code submitted to Judge0, token: {token}")

            # Extract status_id from nested status object
            status_id = data.get("status_id")
            if status_id is None and "status" in data:
                status_id = data["status"].get("id")

            return Judge0SubmissionDTO(
                token=token,
                status_id=status_id,
                stdout=data.get("stdout"),
                stderr=data.get("stderr"),
                time=data.get("time"),
                memory=data.get("memory"),
                compile_output=data.get("compile_output"),
                message=data.get("message"),
            )

        except (Judge0APIError, Judge0ServiceUnavailableError, Judge0ConnectionError, Judge0TimeoutError):
            # Preserve domain exceptions (status/detail from Judge0)
            raise
        except httpx.TimeoutException as e:
            logger.error(f"Judge0 submission timeout: {str(e)}")
            raise Judge0TimeoutError(f"Judge0 submission timed out: {str(e)}")
        except httpx.ConnectError as e:
            logger.error(f"Judge0 connection error: {str(e)}")
            raise Judge0ConnectionError(
                f"Failed to connect to Judge0 API: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Judge0 submission error: {str(e)}", exc_info=True)
            raise Judge0ClientError(f"Failed to submit code to Judge0: {str(e)}")

    async def get_submission_result(
        self, token: str
    ) -> Judge0SubmissionDTO:
        """Get current execution result for a submission token (single poll).

        Returns the latest status without waiting. Use `wait_for_completion()`
        to poll until execution is complete.

        Args:
            token: Judge0 submission token from `submit_code()`

        Returns:
            Judge0SubmissionDTO with current execution status and results

        Raises:
            Judge0APIError: If token not found or API error
            Judge0ConnectionError: If connection fails
            Judge0TimeoutError: If request times out
        """
        client = get_judge0_client()

        try:
            response = await client.get(
                f"/submissions/{token}",
                params={"base64_encoded": "false"},
            )

            if response.status_code == 404:
                raise Judge0APIError(
                    status_code=404,
                    detail=f"Submission token not found: {token}",
                    request_id=response.headers.get("X-Request-ID"),
                )

            if response.status_code != 200:
                await self._handle_api_error(response)

            data = response.json()

            # Extract status_id from nested status object
            status_id = data.get("status_id")
            if status_id is None and "status" in data:
                status_id = data["status"].get("id")

            return Judge0SubmissionDTO(
                token=token,
                status_id=status_id,
                stdout=data.get("stdout"),
                stderr=data.get("stderr"),
                time=data.get("time"),
                memory=data.get("memory"),
                compile_output=data.get("compile_output"),
                message=data.get("message"),
            )

        except (Judge0APIError, Judge0ServiceUnavailableError, Judge0ConnectionError, Judge0TimeoutError) as e:
            # Preserve domain exceptions (status/detail from Judge0)
            logger.warning(f"Judge0 result retrieval error for token {token}: {str(e)}")
            raise
        except httpx.TimeoutException as e:
            logger.error(f"Judge0 result retrieval timeout: {str(e)}")
            raise Judge0TimeoutError(
                f"Judge0 result retrieval timed out: {str(e)}"
            )
        except httpx.ConnectError as e:
            logger.error(f"Judge0 connection error: {str(e)}")
            raise Judge0ConnectionError(
                f"Failed to connect to Judge0 API: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Judge0 result retrieval error: {str(e)}", exc_info=True)
            raise Judge0ClientError(
                f"Failed to get submission result from Judge0: {str(e)}"
            )

    async def wait_for_completion(
        self,
        token: str,
        max_wait_ms: Optional[int] = None,
    ) -> Judge0SubmissionDTO:
        """Poll Judge0 until submission execution is complete.

        Blocks until execution completes (not IN_QUEUE or PROCESSING).
        Respects configured `JUDGE0_API_TIMEOUT` and optional `max_wait_ms`.

        Args:
            token: Judge0 submission token
            max_wait_ms: Optional maximum wait time in milliseconds.
                        If not provided, uses (MAX_POLL_ATTEMPTS * POLL_INTERVAL_MS)

        Returns:
            Judge0SubmissionDTO with final execution status and results

        Raises:
            Judge0TimeoutError: If execution doesn't complete within timeout
            Judge0APIError: If API error occurs
        """
        if max_wait_ms is None:
            max_wait_ms = self.MAX_POLL_ATTEMPTS * self.POLL_INTERVAL_MS

        poll_interval = self.POLL_INTERVAL_MS / 1000  # Convert to seconds
        attempts = 0
        max_attempts = int(max_wait_ms / self.POLL_INTERVAL_MS)

        logger.debug(
            f"Polling Judge0 for token {token}, max_wait={max_wait_ms}ms, "
            f"poll_interval={self.POLL_INTERVAL_MS}ms"
        )

        while attempts < max_attempts:
            try:
                result = await self.get_submission_result(token)

                if result.is_completed:
                    logger.info(
                        f"Judge0 execution completed for token {token}",
                        extra={
                            "status": result.status.name,
                            "attempts": attempts + 1,
                            "time_ms": (attempts + 1) * self.POLL_INTERVAL_MS,
                        },
                    )
                    return result

                attempts += 1
                await asyncio.sleep(poll_interval)

            except Judge0APIError as e:
                if e.status_code == 404:
                    logger.error(f"Submission token not found during polling: {token}")
                raise
            except (Judge0ConnectionError, Judge0TimeoutError):
                # Retry on transient errors
                attempts += 1
                if attempts >= max_attempts:
                    raise
                await asyncio.sleep(poll_interval)

        # Timeout
        elapsed_ms = attempts * self.POLL_INTERVAL_MS
        logger.error(
            f"Judge0 polling timeout for token {token} after {elapsed_ms}ms"
        )
        raise Judge0TimeoutError(
            f"Judge0 execution did not complete within {elapsed_ms}ms timeout"
        )

    async def batch_get_results(
        self, tokens: list[str]
    ) -> dict[str, Judge0SubmissionDTO]:
        """Get execution results for multiple tokens efficiently.

        Batches requests to reduce API calls. Useful for fetching results
        for multiple test case executions.

        Args:
            tokens: List of Judge0 submission tokens

        Returns:
            Dictionary mapping token -> Judge0SubmissionDTO

        Raises:
            ExceptionGroup: If ANY token retrieval fails (partial failures reported)
            Judge0ClientError: If batch retrieval fails
        """
        if not tokens:
            return {}

        results = {}
        errors = {}

        # Fetch in batches to avoid rate limiting
        for i in range(0, len(tokens), self.BATCH_POLL_SIZE):
            batch = tokens[i : i + self.BATCH_POLL_SIZE]

            # Fetch all tokens in parallel (Judge0 supports concurrent requests)
            tasks = [self.get_submission_result(token) for token in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for token, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    errors[token] = result
                else:
                    results[token] = result

        # Surface any errors - don't silently omit failed tokens
        if errors:
            error_messages = [
                f"Token {token}: {str(exc)}" 
                for token, exc in errors.items()
            ]
            logger.error(
                f"Batch result retrieval had {len(errors)} errors out of {len(tokens)} tokens: "
                f"{'; '.join(error_messages)}"
            )
            
            # Raise ExceptionGroup to report all failed tokens
            raise ExceptionGroup(
                f"Judge0 batch result retrieval failed for {len(errors)} token(s)",
                list(errors.values()),
            ) from None

        return results

    async def _handle_api_error(self, response: httpx.Response) -> None:
        """Parse and raise appropriate Judge0 API error.

        Args:
            response: HTTP response from Judge0 API

        Raises:
            Judge0APIError: Appropriately mapped to status code
        """
        try:
            error_data = response.json()
        except Exception:
            error_data = {}

        status_code = response.status_code
        detail = error_data.get("message") or response.text or f"HTTP {status_code}"
        request_id = response.headers.get("X-Request-ID")

        if status_code in (500, 502, 503, 504):
            logger.error(f"Judge0 service error ({status_code}): {detail}")
            if status_code == 502:
                raise Judge0ServiceUnavailableError(detail)
            raise Judge0APIError(
                status_code=status_code,
                detail=detail,
                request_id=request_id,
            )

        raise Judge0APIError(
            status_code=status_code,
            detail=detail,
            request_id=request_id,
        )
