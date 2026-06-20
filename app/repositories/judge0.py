"""Judge0 Repository for code execution operations.

This repository encapsulates all Judge0 API interactions for both "run" (practice)
and "submit" (final) code execution workflows. Common features are centralized here
and reused by service layer implementations.

These operations are NOT persisted in the database (runs are ephemeral).
Only submissions are persisted, handled at the service layer.
"""

import asyncio
import base64
import logging
from typing import Optional, cast

import httpx

from app.core.clients.judge0 import get_judge0_client
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
    POLL_INTERVAL_MS: int = 500
    MAX_POLL_ATTEMPTS: int = 120
    BATCH_POLL_SIZE: int = 20

    def __init__(self) -> None:
        """Initialize Judge0 repository."""
        pass

    @staticmethod
    def _redact_payload_for_debug(payload: dict[str, object]) -> dict[str, object]:
        """Return a redacted preview of a Judge0 payload for debug logging."""

        def truncate(value: object) -> object:
            if not isinstance(value, str):
                return value
            if len(value) <= 120:
                return value
            return f"{value[:120]}...<truncated>"

        redacted = dict(payload)
        for key in ("stdout", "stderr", "compile_output"):
            if key in redacted:
                redacted[key] = truncate(redacted[key])
        return redacted

    def _decode_base64(self, value: str | None) -> str | None:
        """Decode base64 string from Judge0 to UTF-8."""
        if value is None:
            return None
        try:
            return base64.b64decode(value).decode("utf-8")
        except Exception:
            return value

    @staticmethod
    def _encode_base64(value: str) -> str:
        """Encode a UTF-8 string to base64 for Judge0 transport."""
        return base64.b64encode(value.encode("utf-8")).decode("utf-8")

    def _build_submission_payload(
        self,
        request: Judge0ExecutionRequestDTO,
        stdin: str,
        expected_output: str | None,
    ) -> dict[str, object]:
        """Build a single Judge0 submission payload (base64-encoded, with limits).

        Args:
            request: Execution request including source code, language, and limits.
            stdin: Standard input for the program.
            expected_output: Expected output for verdict comparison (optional).

        Returns:
            A dict ready to be JSON-serialized as a Judge0 submission. Execution
            limits are included only when set on the request so unset values fall
            back to the Judge0 instance defaults.
        """
        payload: dict[str, object] = {
            "source_code": self._encode_base64(request.source_code),
            "language_id": request.language_id,
            "stdin": self._encode_base64(stdin),
        }
        if expected_output is not None:
            payload["expected_output"] = self._encode_base64(expected_output)

        # Execution limits (omit when None so Judge0 instance defaults apply).
        if request.cpu_time_limit is not None:
            payload["cpu_time_limit"] = request.cpu_time_limit
        if request.wall_time_limit is not None:
            payload["wall_time_limit"] = request.wall_time_limit
        if request.memory_limit is not None:
            payload["memory_limit"] = request.memory_limit
        if request.stack_limit is not None:
            payload["stack_limit"] = request.stack_limit
        return payload

    def _parse_submission_data(self, data: dict) -> Judge0SubmissionDTO:
        """Map a raw Judge0 submission JSON object to a Judge0SubmissionDTO.

        Args:
            data: Decoded JSON object for a single Judge0 submission.

        Returns:
            A populated Judge0SubmissionDTO. Decodes base64 output fields and
            normalizes the nested ``status`` object to ``status_id``.
        """
        status_id = data.get("status_id")
        if status_id is None and "status" in data:
            status_id = data["status"].get("id")

        token = data.get("token")
        if not token or not isinstance(token, str):
            raise Judge0APIError(
                status_code=500,
                detail=f"Judge0 response missing token: {data}",
            )

        return Judge0SubmissionDTO(
            token=token,
            status_id=status_id,
            stdout=self._decode_base64(data.get("stdout")),
            stderr=self._decode_base64(data.get("stderr")),
            time=data.get("time"),
            memory=data.get("memory"),
            compile_output=self._decode_base64(data.get("compile_output")),
            message=self._decode_base64(data.get("message")),
        )

    async def submit_code(
        self,
        request: Judge0ExecutionRequestDTO,
        stdin: str,
        expected_output: str | None = None,
    ) -> Judge0SubmissionDTO:
        """Submit source code to Judge0 for execution with stdin.

        Submits code immediately without waiting for execution completion.
        Use `wait_for_completion()` to poll results.

        Args:
            request: Execution request with source code, language ID, question ID
            stdin: Standard input for the program (from TestCase.input)
            expected_output: Expected standard output for the program

        Returns:
            Judge0SubmissionDTO with submission token and initial status

        Raises:
            Judge0ClientError: If submission fails
            Judge0ConnectionError: If connection to Judge0 fails
            Judge0TimeoutError: If request times out
        """
        client = get_judge0_client()

        try:
            payload = self._build_submission_payload(request, stdin, expected_output)

            # Submit to Judge0
            response = await client.post(
                "/submissions",
                json=payload,
                params={"base64_encoded": "true", "wait": "false"},
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
                stdout=self._decode_base64(data.get("stdout")),
                stderr=self._decode_base64(data.get("stderr")),
                time=data.get("time"),
                memory=data.get("memory"),
                compile_output=self._decode_base64(data.get("compile_output")),
                message=self._decode_base64(data.get("message")),
            )

        except (
            Judge0APIError,
            Judge0ServiceUnavailableError,
            Judge0ConnectionError,
            Judge0TimeoutError,
        ):
            # Preserve domain exceptions (status/detail from Judge0)
            raise
        except httpx.TimeoutException as e:
            logger.error(f"Judge0 submission timeout: {str(e)}")
            raise Judge0TimeoutError(f"Judge0 submission timed out: {str(e)}")
        except httpx.ConnectError as e:
            logger.error(f"Judge0 connection error: {str(e)}")
            raise Judge0ConnectionError(f"Failed to connect to Judge0 API: {str(e)}")
        except Exception as e:
            logger.error(f"Judge0 submission error: {str(e)}", exc_info=True)
            raise Judge0ClientError(f"Failed to submit code to Judge0: {str(e)}")

    async def get_submission_result(self, token: str) -> Judge0SubmissionDTO:
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
                params={"base64_encoded": "true"},
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

            logger.info(f"DEBUG_GET_RESULT: token={token}, status_id={status_id}")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "DEBUG_GET_RESULT payload: token=%s payload=%s",
                    token,
                    self._redact_payload_for_debug(data),
                )

            return Judge0SubmissionDTO(
                token=token,
                status_id=status_id,
                stdout=self._decode_base64(data.get("stdout")),
                stderr=self._decode_base64(data.get("stderr")),
                time=data.get("time"),
                memory=data.get("memory"),
                compile_output=self._decode_base64(data.get("compile_output")),
                message=self._decode_base64(data.get("message")),
            )

        except (
            Judge0APIError,
            Judge0ServiceUnavailableError,
            Judge0ConnectionError,
            Judge0TimeoutError,
        ) as e:
            # Preserve domain exceptions (status/detail from Judge0)
            logger.warning(f"Judge0 result retrieval error for token {token}: {str(e)}")
            raise
        except httpx.TimeoutException as e:
            logger.error(f"Judge0 result retrieval timeout: {str(e)}")
            raise Judge0TimeoutError(f"Judge0 result retrieval timed out: {str(e)}")
        except httpx.ConnectError as e:
            logger.error(f"Judge0 connection error: {str(e)}")
            raise Judge0ConnectionError(f"Failed to connect to Judge0 API: {str(e)}")
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
        logger.error(f"Judge0 polling timeout for token {token} after {elapsed_ms}ms")
        raise Judge0TimeoutError(
            f"Judge0 execution did not complete within {elapsed_ms}ms timeout"
        )

    async def submit_batch(
        self, submissions: list[tuple[Judge0ExecutionRequestDTO, str, str | None]]
    ) -> list[str | None]:
        """Submit multiple submissions in a single Judge0 batch request.

        Uses the Judge0 CE ``POST /submissions/batch`` endpoint. Submissions are
        chunked by ``config.JUDGE0_BATCH_SIZE`` to bound request size. Tokens are
        returned positionally aligned with the input list; a position is ``None``
        when Judge0 reported a per-item error instead of a token.

        Args:
            submissions: List of ``(request, stdin, expected_output)`` tuples. The
                request carries source code, language, and execution limits.

        Returns:
            A list of Judge0 tokens (or ``None`` for failed items) in input order.

        Raises:
            Judge0ConnectionError: If the connection to Judge0 fails.
            Judge0TimeoutError: If the batch request times out.
            Judge0ClientError: For any other unexpected submission failure.
        """
        from app.core.config import config

        if not submissions:
            return []

        client = get_judge0_client()
        tokens: list[str | None] = []

        try:
            for start in range(0, len(submissions), config.JUDGE0_BATCH_SIZE):
                chunk = submissions[start : start + config.JUDGE0_BATCH_SIZE]
                payload = {
                    "submissions": [
                        self._build_submission_payload(req, stdin, expected)
                        for req, stdin, expected in chunk
                    ]
                }
                response = await client.post(
                    "/submissions/batch",
                    json=payload,
                    params={"base64_encoded": "true"},
                )
                if response.status_code != 201:
                    await self._handle_api_error(response)

                # Judge0 returns a list aligned with the request; failed items are
                # objects without a "token" (e.g. {"error": ...}).
                for item in response.json():
                    token = item.get("token") if isinstance(item, dict) else None
                    tokens.append(token)
                    if not token:
                        logger.error(f"Judge0 batch submission item failed: {item}")

            return tokens

        except (
            Judge0APIError,
            Judge0ServiceUnavailableError,
            Judge0ConnectionError,
            Judge0TimeoutError,
        ):
            raise
        except httpx.TimeoutException as e:
            logger.error(f"Judge0 batch submission timeout: {str(e)}")
            raise Judge0TimeoutError(f"Judge0 batch submission timed out: {str(e)}")
        except httpx.ConnectError as e:
            logger.error(f"Judge0 batch connection error: {str(e)}")
            raise Judge0ConnectionError(f"Failed to connect to Judge0 API: {str(e)}")
        except Exception as e:
            logger.error(f"Judge0 batch submission error: {str(e)}", exc_info=True)
            raise Judge0ClientError(f"Failed to submit batch to Judge0: {str(e)}")

    async def get_batch_results(
        self, tokens: list[str]
    ) -> dict[str, Judge0SubmissionDTO]:
        """Fetch results for many tokens via the Judge0 batch GET endpoint.

        Uses ``GET /submissions/batch?tokens=...``, chunked by
        ``config.JUDGE0_BATCH_SIZE``. Unlike :meth:`batch_get_results`, this issues
        one HTTP request per chunk rather than one per token, which is essential at
        scale. Missing/unknown tokens are simply absent from the returned mapping.

        Args:
            tokens: Judge0 submission tokens to look up.

        Returns:
            Mapping of ``token -> Judge0SubmissionDTO`` for every token Judge0
            returned. Callers should treat absent tokens as "not yet available".

        Raises:
            Judge0ConnectionError: If the connection to Judge0 fails.
            Judge0TimeoutError: If a batch request times out.
            Judge0ClientError: For any other unexpected retrieval failure.
        """
        from app.core.config import config

        if not tokens:
            return {}

        client = get_judge0_client()
        results: dict[str, Judge0SubmissionDTO] = {}

        try:
            for start in range(0, len(tokens), config.JUDGE0_BATCH_SIZE):
                chunk = tokens[start : start + config.JUDGE0_BATCH_SIZE]
                response = await client.get(
                    "/submissions/batch",
                    params={
                        "tokens": ",".join(chunk),
                        "base64_encoded": "true",
                    },
                )
                if response.status_code != 200:
                    await self._handle_api_error(response)

                for item in response.json().get("submissions", []):
                    if not isinstance(item, dict) or not item.get("token"):
                        continue
                    dto = self._parse_submission_data(item)
                    results[dto.token] = dto

            return results

        except (
            Judge0APIError,
            Judge0ServiceUnavailableError,
            Judge0ConnectionError,
            Judge0TimeoutError,
        ):
            raise
        except httpx.TimeoutException as e:
            logger.error(f"Judge0 batch result timeout: {str(e)}")
            raise Judge0TimeoutError(
                f"Judge0 batch result retrieval timed out: {str(e)}"
            )
        except httpx.ConnectError as e:
            logger.error(f"Judge0 batch result connection error: {str(e)}")
            raise Judge0ConnectionError(f"Failed to connect to Judge0 API: {str(e)}")
        except Exception as e:
            logger.error(f"Judge0 batch result error: {str(e)}", exc_info=True)
            raise Judge0ClientError(
                f"Failed to get batch results from Judge0: {str(e)}"
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

        results: dict[str, Judge0SubmissionDTO] = {}
        errors: dict[str, Exception] = {}

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
                    results[token] = cast(Judge0SubmissionDTO, result)

        # Surface any errors - don't silently omit failed tokens
        if errors:
            error_messages = [
                f"Token {token}: {str(exc)}" for token, exc in errors.items()
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

        # Judge0 returns a dict for most errors but a list of per-item errors
        # for batch validation failures (e.g. malformed submissions array).
        if isinstance(error_data, list):
            detail = "; ".join(str(item) for item in error_data) or response.text
        elif isinstance(error_data, dict):
            detail = error_data.get("message") or response.text
        else:
            detail = response.text

        status_code = response.status_code
        detail = detail or f"HTTP {status_code}"
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
