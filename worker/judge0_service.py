import asyncio
from typing import Sequence
from uuid import UUID

from app.core.logger import logger
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
) -> SubmissionTestCase:
    return SubmissionTestCase(
        submission_id=submission_id,
        testcase_id=testcase.id,
        status=status,
        stdout=result.stdout,
        stderr=result.stderr or result.compile_output,
        time=int(result.time * 1000) if result.time is not None else None,
        memory=result.memory,
    )


class Judge0EvaluationService:
    """Service to handle core code execution on Judge0."""

    def __init__(self, judge0_repo: Judge0Repository | None = None) -> None:
        self.judge0_repo = judge0_repo or Judge0Repository()

    async def run_evaluation(
        self,
        submission_id: UUID,
        question_id: UUID,
        language_id: int,
        testcases: Sequence[TestCase] | Sequence[QuestionTestCaseResponse],
        final_source_code: str,
    ) -> EvaluationResult:
        """Run concurrent Judge0 evaluations and return the evaluation result."""
        request_dto = Judge0ExecutionRequestDTO(
            question_id=str(question_id),
            source_code=final_source_code,
            language_id=language_id,
        )

        total_time = 0.0
        max_memory = 0
        passed_cases = 0

        testcase_results = []
        final_status = SubmissionStatus.AC

        # 1. Submit all test cases to Judge0 in parallel
        submit_tasks = [
            self.judge0_repo.submit_code(
                request=request_dto,
                stdin=testcase.input,
                expected_output=testcase.output,
            )
            for testcase in testcases
        ]
        submission_results = await asyncio.gather(*submit_tasks, return_exceptions=True)

        # 2. Filter out failed submissions and build wait tasks
        wait_tasks = []
        for testcase, sub_res in zip(testcases, submission_results):
            if isinstance(sub_res, Exception):
                wait_tasks.append(None)
            else:
                wait_tasks.append(self.judge0_repo.wait_for_completion(sub_res.token))

        # 3. Poll for completion of successfully submitted tasks in parallel
        actual_wait_tasks = [t for t in wait_tasks if t is not None]
        if actual_wait_tasks:
            completed_results = await asyncio.gather(
                *actual_wait_tasks, return_exceptions=True
            )
        else:
            completed_results = []

        # 4. Map completed results back to the original list order
        completed_iter = iter(completed_results)
        results = []
        for sub_res, wait_task in zip(submission_results, wait_tasks):
            if isinstance(sub_res, Exception):
                results.append(sub_res)
            elif wait_task is None:
                results.append(Exception("Submission failed to initialize"))
            else:
                results.append(next(completed_iter))

        # 5. Process all results and aggregate stats
        for testcase, result in zip(testcases, results):
            if isinstance(result, Exception):
                logger.error(
                    f"Error evaluating testcase {testcase.id}: {result}", exc_info=True
                )
                final_status = SubmissionStatus.SYSTEM_ERROR
                stc = SubmissionTestCase(
                    submission_id=submission_id,
                    testcase_id=testcase.id,
                    status=SubmissionStatus.SYSTEM_ERROR,
                    stderr=str(result),
                )
                testcase_results.append(stc)
                continue

            logger.info(f"Code Result: {result}")
            # Map status
            status = JUDGE0_TO_SUBMISSION_STATUS.get(
                result.status, SubmissionStatus.SYSTEM_ERROR
            )

            # Record stats
            if result.time is not None:
                total_time += result.time
            if result.memory is not None:
                max_memory = max(max_memory, result.memory)

            # Create testcase record
            stc = create_submission_testcase(submission_id, testcase, result, status)
            testcase_results.append(stc)

            if status == SubmissionStatus.AC:
                passed_cases += 1
            else:
                if final_status == SubmissionStatus.AC:
                    final_status = status

        return EvaluationResult(
            status=final_status,
            passed_testcases=passed_cases,
            total_testcases=len(testcases),
            total_time=int(total_time * 1000),
            total_memory=max_memory,
            testcase_results=testcase_results,
        )
