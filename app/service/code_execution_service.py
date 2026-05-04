"""Service layer for code execution (practice "Run" operation)."""

import asyncio
import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clients.judge0 import Judge0StatusCode
from app.core.logger import logger
from app.exceptions.execution import (
    CodeExecutionError,
    CompilationError,
    NoTestCasesError,
)
from app.exceptions.judge0 import Judge0ClientError, Judge0TimeoutError
from app.repositories.dto.judge0 import (
    Judge0ExecutionRequestDTO,
    Judge0ExecutionResultDTO,
    Judge0SubmissionDTO,
)
from app.repositories.judge0 import Judge0Repository
from app.repositories.question import QuestionRepository
from app.repositories.testcase import TestCaseRepository
from app.schema.execution import CodeRunResponse, DraftCodeRunRequest, TestCaseRunResult
from app.utils.enums import ExecutionStatus

JUDGE0_TO_EXECUTION_STATUS: dict[Judge0StatusCode, ExecutionStatus] = {
    Judge0StatusCode.ACCEPTED: ExecutionStatus.ACCEPTED,
    Judge0StatusCode.WRONG_ANSWER: ExecutionStatus.WRONG_ANSWER,
    Judge0StatusCode.TIME_LIMIT_EXCEEDED: ExecutionStatus.TIME_LIMIT_EXCEEDED,
    Judge0StatusCode.RUNTIME_ERROR: ExecutionStatus.RUNTIME_ERROR,
    Judge0StatusCode.MEMORY_LIMIT_EXCEEDED: ExecutionStatus.MEMORY_LIMIT_EXCEEDED,
    Judge0StatusCode.CPU_TIME_LIMIT_EXCEEDED: ExecutionStatus.CPU_TIME_LIMIT_EXCEEDED,
    Judge0StatusCode.SYSTEM_ERROR: ExecutionStatus.SYSTEM_ERROR,
    Judge0StatusCode.INTERNAL_ERROR: ExecutionStatus.INTERNAL_ERROR,
}


class CodeExecutionService:
    """Service for executing user code against test cases in practice mode."""

    def __init__(self, db: AsyncSession):
        """Initialize service with async database session.

        Args:
            db: SQLAlchemy AsyncSession for database operations
        """
        self.db = db
        self.question_repo = QuestionRepository(db)
        self.testcase_repo = TestCaseRepository(db)
        self.judge0_repo = Judge0Repository()

    @staticmethod
    def _redact_first_result_for_debug(
        result: Judge0SubmissionDTO,
    ) -> dict[str, object]:
        """Build a redacted debug payload for the first Judge0 result."""

        def truncate(value: str | None, *, limit: int = 160) -> str | None:
            if value is None:
                return None
            if len(value) <= limit:
                return value
            return f"{value[:limit]}...<truncated>"

        def mask_message(value: str | None) -> str | None:
            if value is None:
                return None
            masked = re.sub(
                r"(?i)\b(password|secret|token|api[_-]?key|authorization)\b\s*[:=]\s*[^\s,;]+",
                r"\1=<redacted>",
                value,
            )
            return truncate(masked, limit=240)

        return {
            "token": result.token,
            "status_id": result.status_id,
            "status": result.status.name,
            "stdout": truncate(result.stdout),
            "compile_output": truncate(result.compile_output),
            "message": mask_message(result.message),
        }

    async def run_code(
        self,
        question_id: UUID,
        source_code: str,
        language_id: int,
    ) -> CodeRunResponse:
        """Execute user code against all non-hidden test cases.

        Args:
            question_id: UUID of question to run code against
            source_code: User-submitted source code (1-50KB)
            language_id: Judge0 language ID (e.g., 71 for Python)

        Returns:
            CodeRunResponse with testcases, total count, and passed count

        Raises:
            QuestionNotFoundError: If question_id doesn't exist
            NoTestCasesError: If question has no non-hidden test cases
            CompilationError: If code fails to compile (HTTP 400)
            CodeExecutionError: If Judge0 service fails (HTTP 502)
            Judge0TimeoutError: If polling times out
        """
        logger.info(f"Starting code execution for question {question_id}")

        question = await self.question_repo.get_question_or_raise(question_id)
        logger.debug(
            f"Question found: {question.question_text[:50]}... (id={question.id})"
        )

        testcases = await self.testcase_repo.get_non_hidden_by_question(question_id)
        if not testcases:
            logger.warning(f"No non-hidden test cases for question {question_id}")
            raise NoTestCasesError(f"Question {question_id} has no visible test cases")

        logger.info(
            f"Found {len(testcases)} non-hidden test cases for question {question_id}"
        )

        request = Judge0ExecutionRequestDTO(
            question_id=str(question_id),
            source_code=source_code,
            language_id=language_id,
        )

        logger.debug(f"Submitting code to Judge0 for {len(testcases)} test cases")
        submit_tasks = [
            self.judge0_repo.submit_code(request, tc.input) for tc in testcases
        ]
        submissions = await asyncio.gather(*submit_tasks)

        token_to_testcase = {sub.token: tc for sub, tc in zip(submissions, testcases)}
        all_tokens = [sub.token for sub in submissions]

        logger.debug(f"Submitted {len(all_tokens)} submissions to Judge0")

        first_token = all_tokens[0]
        logger.debug("Checking compilation on first test case")
        first_result = await self.judge0_repo.wait_for_completion(first_token)

        logger.info(
            f"DEBUG_FIRST_RESULT: token={first_token}, status_id={first_result.status_id}, status={first_result.status.name}"
        )
        if logger.isEnabledFor(10):
            logger.debug(
                "DEBUG_FIRST_RESULT payload: question_id=%s token=%s status_id=%s payload=%s",
                question_id,
                first_token,
                first_result.status_id,
                self._redact_first_result_for_debug(first_result),
            )

        if first_result.status == Judge0StatusCode.COMPILATION_ERROR:
            compile_error = (
                first_result.compile_output
                or first_result.message
                or "Compilation error"
            )
            logger.warning(
                f"Compilation error for question {question_id}: {compile_error}"
            )
            raise CompilationError(compile_error)

        # Check stderr for compilation errors (Python, Ruby, etc. report SyntaxError during execution)
        if (
            first_result.status == Judge0StatusCode.INTERNAL_ERROR
            and first_result.stderr
        ):
            stderr_lower = first_result.stderr.lower()
            compilation_error_indicators = [
                "syntaxerror",
                "indentationerror",
                "taberror",
                "importerror",
                "modulenotfounderror",
                "nameerror: name",  # Common in Python tests
                "typeerror",
                "attributeerror",
            ]
            if any(
                indicator in stderr_lower for indicator in compilation_error_indicators
            ):
                logger.warning(
                    f"Detected compilation-like error in stderr for question {question_id}: {first_result.stderr[:200]}"
                )
                raise CompilationError(first_result.stderr or "Code execution failed")

        if first_result.status in (
            Judge0StatusCode.SYSTEM_ERROR,
            Judge0StatusCode.INTERNAL_ERROR,
        ):
            error_msg = (
                first_result.message
                or f"Judge0 infrastructure error (Status: {first_result.status.name})"
            )
            logger.error(
                f"Judge0 service error for question {question_id}: {error_msg}"
            )
            raise CodeExecutionError(
                f"Judge0 failed to execute the submission: {error_msg}"
            )

        first_testcase = token_to_testcase[first_token]
        first_stdout = (first_result.stdout or "").strip()
        first_expected = (first_testcase.output or "").strip()
        first_execution = Judge0ExecutionResultDTO(
            question_id=str(question_id),
            testcase_id=str(first_testcase.id),
            status=first_result.status,
            passed=(first_stdout == first_expected),
            stdout=first_result.stdout,
            stderr=first_result.stderr,
            expected_output=first_testcase.output,
            time=first_result.time,
            memory=first_result.memory,
        )
        all_execution_results: list[Judge0ExecutionResultDTO] = [first_execution]

        remaining_tokens = all_tokens[1:]
        if remaining_tokens:
            logger.debug(
                f"Batch polling {len(remaining_tokens)} remaining submissions until completion"
            )
            try:
                batch_results: dict[str, Judge0SubmissionDTO] = {}
                pending_tokens = set(remaining_tokens)
                poll_interval = self.judge0_repo.POLL_INTERVAL_MS / 1000
                attempts = 0
                max_attempts = self.judge0_repo.MAX_POLL_ATTEMPTS

                while attempts < max_attempts and pending_tokens:
                    current_batch = await self.judge0_repo.batch_get_results(
                        list(pending_tokens)
                    )
                    batch_results.update(current_batch)

                    remaining_pending = []
                    for token in pending_tokens:
                        pending_result = batch_results.get(token)
                        if pending_result and not pending_result.is_completed:
                            remaining_pending.append(token)

                    if not remaining_pending:
                        logger.info(
                            f"All {len(remaining_tokens)} remaining submissions completed"
                        )
                        break

                    pending_tokens = set(remaining_pending)
                    attempts += 1
                    if pending_tokens and attempts < max_attempts:
                        await asyncio.sleep(poll_interval)
                        logger.debug(
                            f"Still waiting for {len(pending_tokens)} submissions to complete (attempt {attempts}/{max_attempts})"
                        )

                if pending_tokens and attempts >= max_attempts:
                    elapsed_ms = attempts * self.judge0_repo.POLL_INTERVAL_MS
                    error_msg = f"Batch polling timeout after {elapsed_ms}ms with {len(pending_tokens)} submissions still pending"
                    logger.error(error_msg)
                    raise Judge0TimeoutError(error_msg)
            except ExceptionGroup as eg:
                logger.error(f"Batch retrieval failures: {eg}")
                raise Judge0ClientError(
                    f"Failed to retrieve results for {len(eg.exceptions)} submission(s) from Judge0"
                )

            for token in remaining_tokens:
                submission_result = batch_results.get(token)
                if not submission_result:
                    logger.warning(f"No result for token {token}, skipping")
                    continue

                if submission_result.status in (
                    Judge0StatusCode.SYSTEM_ERROR,
                    Judge0StatusCode.INTERNAL_ERROR,
                ):
                    error_msg = (
                        submission_result.message
                        or f"Judge0 infrastructure error (Status: {submission_result.status.name})"
                    )
                    logger.error(
                        f"Judge0 service error on remaining submission {token}: {error_msg}"
                    )
                    raise CodeExecutionError(
                        f"Judge0 failed to execute submission {token}: {error_msg}"
                    )

                testcase = token_to_testcase[token]
                testcase_stdout = (submission_result.stdout or "").strip()
                testcase_expected = (testcase.output or "").strip()
                execution_result = Judge0ExecutionResultDTO(
                    question_id=str(question_id),
                    testcase_id=str(testcase.id),
                    status=submission_result.status,
                    passed=(testcase_stdout == testcase_expected),
                    stdout=submission_result.stdout,
                    stderr=submission_result.stderr,
                    expected_output=testcase.output,
                    time=submission_result.time,
                    memory=submission_result.memory,
                )
                all_execution_results.append(execution_result)

        logger.debug(f"Mapping {len(all_execution_results)} results to response schema")
        testcase_results: list[TestCaseRunResult] = []
        for execution_result in all_execution_results:
            execution_status = JUDGE0_TO_EXECUTION_STATUS.get(
                execution_result.status,
                ExecutionStatus.RUNTIME_ERROR,
            )
            if execution_result.status not in JUDGE0_TO_EXECUTION_STATUS:
                logger.warning(
                    f"Unmapped Judge0 status {execution_result.status.name}, "
                    f"defaulting to RUNTIME_ERROR"
                )
            testcase_result = TestCaseRunResult(
                testcase_id=execution_result.testcase_id,
                status=execution_status,
                passed=execution_result.passed,
                stdout=execution_result.stdout,
                stderr=execution_result.stderr,
                expected_output=execution_result.expected_output,
                time=execution_result.time,
                memory=execution_result.memory,
            )
            testcase_results.append(testcase_result)

        total_tests = len(testcase_results)
        passed_tests = sum(1 for result in testcase_results if result.passed)

        logger.info(
            f"Code execution completed for question {question_id}: "
            f"{passed_tests}/{total_tests} tests passed"
        )

        return CodeRunResponse(
            testcases=testcase_results,
            total=total_tests,
            passed=passed_tests,
        )

    async def run_draft_code(
        self,
        request: DraftCodeRunRequest,
    ) -> CodeRunResponse:
        """Execute draft code against provided ephemeral test cases.

        Args:
            request: Draft code run request with code components and test cases

        Returns:
            CodeRunResponse with testcase results

        Raises:
            CompilationError: If code fails to compile
            CodeExecutionError: If Judge0 service fails
            Judge0TimeoutError: If polling times out
        """
        logger.info(f"Starting draft code execution for language {request.language_id}")

        # Combine code components
        # Note: Order is starter -> solution -> driver
        # We add newlines to ensure no syntax issues from concatenation
        source_code = f"{request.solution_code}\n\n{request.driver_code}"

        # Build Judge0 request DTO
        # We use a dummy UUID string for question_id since it's a draft
        judge0_request = Judge0ExecutionRequestDTO(
            question_id="draft",
            source_code=source_code,
            language_id=request.language_id,
        )

        logger.debug(
            f"Submitting draft code to Judge0 for {len(request.test_cases)} test cases"
        )
        submit_tasks = [
            self.judge0_repo.submit_code(judge0_request, tc.input)
            for tc in request.test_cases
        ]
        submissions = await asyncio.gather(*submit_tasks)

        token_to_testcase = {
            sub.token: tc for sub, tc in zip(submissions, request.test_cases)
        }
        all_tokens = [sub.token for sub in submissions]

        logger.debug(f"Submitted {len(all_tokens)} draft submissions to Judge0")

        first_token = all_tokens[0]
        first_result = await self.judge0_repo.wait_for_completion(first_token)

        if first_result.status == Judge0StatusCode.COMPILATION_ERROR:
            compile_error = (
                first_result.compile_output
                or first_result.message
                or "Compilation error"
            )
            raise CompilationError(compile_error)

        # Check stderr for compilation errors (Python, etc.)
        if (
            first_result.status == Judge0StatusCode.INTERNAL_ERROR
            and first_result.stderr
        ):
            stderr_lower = first_result.stderr.lower()
            if any(
                ind in stderr_lower
                for ind in [
                    "syntaxerror",
                    "indentationerror",
                    "taberror",
                    "importerror",
                    "modulenotfounderror",
                    "nameerror: name",
                    "typeerror",
                    "attributeerror",
                ]
            ):
                raise CompilationError(first_result.stderr or "Code execution failed")

        if first_result.status in (
            Judge0StatusCode.SYSTEM_ERROR,
            Judge0StatusCode.INTERNAL_ERROR,
        ):
            error_msg = first_result.message or "Judge0 infrastructure error"
            raise CodeExecutionError(error_msg)

        # Map first result
        first_testcase = token_to_testcase[first_token]
        first_stdout = (first_result.stdout or "").strip()
        first_expected = (first_testcase.expected_output or "").strip()
        first_execution = Judge0ExecutionResultDTO(
            question_id="draft",
            testcase_id="draft_0",
            status=first_result.status,
            passed=(first_stdout == first_expected),
            stdout=first_result.stdout,
            stderr=first_result.stderr,
            expected_output=first_testcase.expected_output,
            time=first_result.time,
            memory=first_result.memory,
        )
        all_execution_results: list[Judge0ExecutionResultDTO] = [first_execution]

        remaining_tokens = all_tokens[1:]
        if remaining_tokens:
            batch_results = await self.judge0_repo.batch_get_results(remaining_tokens)

            # Note: We need to wait for completion for all in batch if not already done
            # But batch_get_results just gets the current status.
            # Wait, the run_code method handles the polling loop for remaining tokens.
            # I should use the same polling logic.

            # Re-implementing the polling loop for draft
            pending_tokens = set(remaining_tokens)
            poll_interval = self.judge0_repo.POLL_INTERVAL_MS / 1000
            attempts = 0
            max_attempts = self.judge0_repo.MAX_POLL_ATTEMPTS

            while attempts < max_attempts and pending_tokens:
                current_batch = await self.judge0_repo.batch_get_results(
                    list(pending_tokens)
                )
                batch_results.update(current_batch)

                remaining_pending = [
                    t
                    for t in pending_tokens
                    if t in batch_results and not batch_results[t].is_completed
                ]
                if not remaining_pending:
                    break
                pending_tokens = set(remaining_pending)
                attempts += 1
                await asyncio.sleep(poll_interval)
            if pending_tokens and attempts >= max_attempts:
                elapsed_ms = attempts * self.judge0_repo.POLL_INTERVAL_MS
                error_msg = f"Draft polling timeout after {elapsed_ms}ms with {len(pending_tokens)} submissions still pending"
                logger.error(error_msg)
                raise Judge0TimeoutError(error_msg)

            for i, token in enumerate(remaining_tokens, 1):
                submission_result = batch_results.get(token)
                if not submission_result:
                    continue

                testcase = token_to_testcase[token]
                testcase_stdout = (submission_result.stdout or "").strip()
                testcase_expected = (testcase.expected_output or "").strip()

                all_execution_results.append(
                    Judge0ExecutionResultDTO(
                        question_id="draft",
                        testcase_id=f"draft_{i}",
                        status=submission_result.status,
                        passed=(testcase_stdout == testcase_expected),
                        stdout=submission_result.stdout,
                        stderr=submission_result.stderr,
                        expected_output=testcase.expected_output,
                        time=submission_result.time,
                        memory=submission_result.memory,
                    )
                )

        testcase_results: list[TestCaseRunResult] = []
        for i, res in enumerate(all_execution_results):
            testcase_results.append(
                TestCaseRunResult(
                    testcase_id=f"draft_{i}",
                    status=JUDGE0_TO_EXECUTION_STATUS.get(
                        res.status, ExecutionStatus.RUNTIME_ERROR
                    ),
                    passed=res.passed,
                    stdout=res.stdout,
                    stderr=res.stderr,
                    expected_output=res.expected_output,
                    time=res.time,
                    memory=res.memory,
                )
            )

        return CodeRunResponse(
            testcases=testcase_results,
            total=len(testcase_results),
            passed=sum(1 for r in testcase_results if r.passed),
        )
