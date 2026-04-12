"""Service layer for code execution (practice "Run" operation).

Orchestrates repositories to run user code against non-hidden test cases.
Handles the complete flow:
1. Fetch question and test cases
2. Submit code for execution
3. Check compilation error
4. Poll results efficiently
5. Map to response schema
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clients.judge0 import Judge0StatusCode
from app.core.logger import logger
from app.exceptions.execution import CompilationError, NoTestCasesError
from app.repositories.dto.judge0 import Judge0ExecutionRequestDTO, Judge0ExecutionResultDTO
from app.repositories.judge0 import Judge0Repository
from app.repositories.question import QuestionRepository
from app.repositories.testcase import TestCaseRepository
from app.schema.execution import CodeRunResponse, TestCaseRunResult


class CodeExecutionService:
    """Service for executing user code against test cases in practice mode.
    
    Handles the orchestration of:
    - Fetching question and test cases from database
    - Submitting code to Judge0 for execution
    - Efficiently polling for results (batch + parallel)
    - Mapping results to API response schema
    
    Only executes against NON-HIDDEN test cases (practice mode).
    """

    def __init__(self, db: AsyncSession):
        """Initialize service with async database session.

        Args:
            db: SQLAlchemy AsyncSession for database operations
        """
        self.db = db
        self.question_repo = QuestionRepository(db)
        self.testcase_repo = TestCaseRepository(db)
        self.judge0_repo = Judge0Repository()

    async def run_code(
        self,
        question_id: UUID,
        source_code: str,
        language_id: int,
    ) -> CodeRunResponse:
        """Execute user code against all non-hidden test cases.

        Main orchestration method that:
        1. Validates question exists
        2. Fetches non-hidden test cases
        3. Submits code to Judge0 for each test case
        4. Checks compilation error (early exit if found)
        5. Batch polls all remaining results efficiently
        6. Maps ExecutionResultDTOs to TestCaseRunResult schema
        7. Returns aggregated CodeRunResponse

        Args:
            question_id: UUID of question to run code against
            source_code: User-submitted source code (1-50KB)
            language_id: Judge0 language ID (e.g., 71 for Python)

        Returns:
            CodeRunResponse with:
            - testcases: list of TestCaseRunResult (one per test case)
            - total: number of test cases executed
            - passed: number of test cases that passed

        Raises:
            QuestionNotFoundError: If question_id doesn't exist
            NoTestCasesError: If question has no non-hidden test cases
            Judge0ClientError: If Judge0 API call fails
            Judge0TimeoutError: If execution polling times out
        """
        logger.info(f"Starting code execution for question {question_id}")

        # Step 1: Validate question exists
        question = await self.question_repo.get_question_or_raise(question_id)
        logger.debug(f"Question found: {question.question_text[:50]}... (id={question.id})")

        # Step 2: Fetch NON-HIDDEN test cases only (practice mode)
        testcases = await self.testcase_repo.get_non_hidden_by_question(question_id)
        if not testcases:
            logger.warning(f"No non-hidden test cases for question {question_id}")
            raise NoTestCasesError(
                f"Question {question_id} has no visible test cases"
            )

        logger.info(
            f"Found {len(testcases)} non-hidden test cases for question {question_id}"
        )

        # Step 3: Create execution request DTO
        request = Judge0ExecutionRequestDTO(
            question_id=str(question_id),
            source_code=source_code,
            language_id=language_id,
        )

        # Step 4: Submit code for each test case (parallel)
        logger.debug(f"Submitting code to Judge0 for {len(testcases)} test cases")
        submit_tasks = [
            self.judge0_repo.submit_code(request, tc.input) for tc in testcases
        ]
        import asyncio
        submissions = await asyncio.gather(*submit_tasks)

        # Create token -> testcase mapping
        token_to_testcase = {
            sub.token: tc for sub, tc in zip(submissions, testcases)
        }
        all_tokens = [sub.token for sub in submissions]

        logger.debug(f"Submitted {len(all_tokens)} submissions to Judge0")

        # Step 5: Check compilation on FIRST test case
        first_token = all_tokens[0]
        logger.debug("Checking compilation on first test case")
        first_result = await self.judge0_repo.wait_for_completion(first_token)

        # Early exit if compilation error or internal error
        if first_result.status in (Judge0StatusCode.COMPILATION_ERROR, Judge0StatusCode.INTERNAL_ERROR):
            compile_error = (
                first_result.compile_output
                or first_result.message
                or f"Compilation/Internal error (Status: {first_result.status.name})"
            )
            logger.warning(
                f"Compilation/Internal error for question {question_id}: {compile_error}"
            )
            # Raise so route handler can return CompilationErrorResponse
            raise CompilationError(compile_error)

        # Step 6: Map first result to ExecutionResultDTO
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
        all_execution_results = [first_execution]

        # Step 7: Batch poll REMAINING test cases (if any)
        remaining_tokens = all_tokens[1:]
        if remaining_tokens:
            logger.debug(f"Batch polling {len(remaining_tokens)} remaining submissions")
            batch_results = await self.judge0_repo.batch_get_results(remaining_tokens)

            for token in remaining_tokens:
                submission_result = batch_results.get(token)
                if not submission_result:
                    logger.warning(f"No result for token {token}, skipping")
                    continue

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

        # Step 8: Map ExecutionResultDTOs to TestCaseRunResult schema
        logger.debug(f"Mapping {len(all_execution_results)} results to response schema")
        testcase_results = []
        for execution_result in all_execution_results:
            result = TestCaseRunResult(
                testcase_id=execution_result.testcase_id,
                status=execution_result.status.name,  # e.g., "ACCEPTED"
                passed=execution_result.passed,
                stdout=execution_result.stdout,
                stderr=execution_result.stderr,
                expected_output=execution_result.expected_output,
                time=execution_result.time,
                memory=execution_result.memory,
            )
            testcase_results.append(result)

        # Step 9: Calculate summary statistics
        total_tests = len(testcase_results)
        passed_tests = sum(1 for result in testcase_results if result.passed)

        logger.info(
            f"Code execution completed for question {question_id}: "
            f"{passed_tests}/{total_tests} tests passed"
        )

        # Step 10: Return CodeRunResponse
        response = CodeRunResponse(
            testcases=testcase_results,
            total=total_tests,
            passed=passed_tests,
        )

        return response


# Import after class definition to avoid circular imports (already imported at top now)
