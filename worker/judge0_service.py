from typing import Sequence
from uuid import UUID

from app.models.question import SubmissionTestCase, TestCase
from app.repositories.dto.evaluation import EvaluationResult
from app.repositories.dto.judge0 import Judge0ExecutionRequestDTO, Judge0SubmissionDTO
from app.repositories.judge0 import Judge0Repository
from app.schema.question import QuestionTestCaseResponse
from app.utils.enums import SubmissionStatus
from app.utils.mapper import JUDGE0_TO_SUBMISSION_STATUS


def create_submission_testcase(
    submission_id: UUID,
    testcase: TestCase | QuestionTestCaseResponse,
    result: Judge0SubmissionDTO,
    status: SubmissionStatus,
    token: str | None = None,
) -> SubmissionTestCase:
    """Build a SubmissionTestCase row from a Judge0 result.

    Args:
        submission_id: Owning submission id.
        testcase: The testcase that was executed.
        result: The Judge0 result DTO for this testcase.
        status: Mapped platform verdict for this testcase.
        token: Judge0 token, persisted for audit/recovery.

    Returns:
        An unsaved SubmissionTestCase ORM row.
    """
    return SubmissionTestCase(
        submission_id=submission_id,
        testcase_id=testcase.id,
        status=status,
        judge0_token=token,
        stdout=result.stdout,
        stderr=result.stderr or result.compile_output,
        time=int(result.time * 1000) if result.time is not None else None,
        memory=result.memory,
    )


class Judge0EvaluationService:
    """Service to handle core code execution on Judge0."""

    def __init__(self, judge0_repo: Judge0Repository | None = None) -> None:
        self.judge0_repo = judge0_repo or Judge0Repository()

    async def submit_testcases(
        self,
        request_dto: Judge0ExecutionRequestDTO,
        testcases: Sequence[TestCase] | Sequence[QuestionTestCaseResponse],
    ) -> list[str | None]:
        """Batch-submit every testcase to Judge0 without waiting for results.

        This is the SUBMIT stage of the decoupled pipeline: it returns quickly
        with one Judge0 token per testcase (or ``None`` where submission failed),
        positionally aligned with ``testcases``.

        Args:
            request_dto: Execution request carrying source code, language, and
                the (already-capped) execution limits.
            testcases: Testcases to execute, each providing ``input``/``output``.

        Returns:
            A list of Judge0 tokens (or ``None``) in ``testcases`` order.
        """
        submissions = [
            (request_dto, testcase.input, testcase.output) for testcase in testcases
        ]
        return await self.judge0_repo.submit_batch(submissions)

    def build_evaluation_result(
        self,
        submission_id: UUID,
        testcases: Sequence[TestCase] | Sequence[QuestionTestCaseResponse],
        tokens: Sequence[str | None],
        results_by_token: dict[str, Judge0SubmissionDTO],
        timed_out: bool = False,
    ) -> EvaluationResult:
        """Aggregate fetched Judge0 results into a final EvaluationResult.

        This is the PERSIST-stage aggregation: it maps each testcase to its
        Judge0 result (looked up by token) and computes the overall verdict and
        resource totals. Missing results are recorded as SYSTEM_ERROR (or TLE
        when ``timed_out`` is set), never silently dropped.

        Args:
            submission_id: Owning submission id.
            testcases: Testcases that were executed (aligned with ``tokens``).
            tokens: Judge0 tokens per testcase (``None`` where submit failed).
            results_by_token: Mapping of token -> result DTO fetched from Judge0.
            timed_out: When True, treat unresolved testcases as TLE instead of
                SYSTEM_ERROR (the poller deadline elapsed).

        Returns:
            The aggregated EvaluationResult, ready to persist.
        """
        total_time = 0.0
        max_memory = 0
        passed_cases = 0
        testcase_results: list[SubmissionTestCase] = []
        final_status = SubmissionStatus.AC

        missing_status = (
            SubmissionStatus.TLE if timed_out else SubmissionStatus.SYSTEM_ERROR
        )

        for testcase, token in zip(testcases, tokens):
            result = results_by_token.get(token) if token else None

            if result is None:
                if final_status == SubmissionStatus.AC:
                    final_status = missing_status
                testcase_results.append(
                    SubmissionTestCase(
                        submission_id=submission_id,
                        testcase_id=testcase.id,
                        status=missing_status,
                        judge0_token=token,
                        stderr=(
                            "Execution timed out"
                            if timed_out
                            else "No result returned by Judge0"
                        ),
                    )
                )
                continue

            try:
                status = JUDGE0_TO_SUBMISSION_STATUS.get(
                    result.status, SubmissionStatus.SYSTEM_ERROR
                )
            except Exception:
                # status_id missing/unknown -> treat as a system error for this case.
                status = SubmissionStatus.SYSTEM_ERROR
            if result.time is not None:
                total_time += result.time
            if result.memory is not None:
                max_memory = max(max_memory, result.memory)

            testcase_results.append(
                create_submission_testcase(
                    submission_id, testcase, result, status, token=token
                )
            )

            if status == SubmissionStatus.AC:
                passed_cases += 1
            elif final_status == SubmissionStatus.AC:
                final_status = status

        return EvaluationResult(
            status=final_status,
            passed_testcases=passed_cases,
            total_testcases=len(testcases),
            total_time=int(total_time * 1000),
            total_memory=max_memory,
            testcase_results=testcase_results,
        )
