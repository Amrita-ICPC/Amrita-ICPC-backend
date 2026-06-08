import asyncio
from typing import Sequence
from uuid import UUID

from app.core.clients.celery import celery_app
from app.core.clients.database import SessionLocal
from app.core.logger import logger
from app.exceptions.question import InvalidQuestionError
from app.models.question import Submission, SubmissionTestCase, TestCase
from app.repositories.dto.evaluation import EvaluationResult
from app.repositories.dto.judge0 import Judge0ExecutionRequestDTO, Judge0SubmissionDTO
from app.repositories.judge0 import Judge0Repository
from app.repositories.question import QuestionRepository
from app.schema.student.submission import (
    StudentSubmissionUpdateEvent,
    StudentSubmissionUpdatePayload,
)
from app.service.contest_event_service import ContestEventService
from app.utils.enums import SubmissionStatus
from app.utils.mapper import JUDGE0_TO_SUBMISSION_STATUS
from app.validators.question import QuestionValidator


def create_submission_testcase(
    submission_id: UUID,
    testcase: TestCase,
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


async def _run_evaluation(
    submission: Submission,
    testcases: Sequence[TestCase],
    repo: Judge0Repository,
    final_source_code: str,
) -> EvaluationResult:
    """Run concurrent Judge0 evaluations and return the evaluation result."""
    request_dto = Judge0ExecutionRequestDTO(
        question_id=str(submission.question_id),
        source_code=final_source_code,
        language_id=submission.language_id,
    )

    total_time = 0.0
    max_memory = 0
    passed_cases = 0

    testcase_results = []
    final_status = SubmissionStatus.AC

    # 1. Submit all test cases to Judge0 in parallel
    submit_tasks = [
        repo.submit_code(
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
            wait_tasks.append(repo.wait_for_completion(sub_res.token))

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
                submission_id=submission.id,
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
        stc = create_submission_testcase(submission.id, testcase, result, status)
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


async def _evaluate_submission_async(submission_id: UUID) -> None:
    """Async helper to evaluate submission."""
    async with SessionLocal() as db:
        repository = QuestionRepository(db)
        event_service = ContestEventService()

        # 1. Query the submission id via repository
        submission = await repository.get_submission(submission_id)
        if submission is None:
            logger.error(f"Submission not found: {submission_id}")
            return

        if submission.status != SubmissionStatus.QUEUED:
            logger.warning(
                f"Submission {submission_id} is not QUEUED, aborting evaluation."
            )
            return

        logger.info(
            f"Retrieved submission {submission.id} for question {submission.question_id}"
        )

        # Check if it has contest association for event publishing
        contest_id = None
        team_id = None
        contest_team_member_id = None
        if submission.contest_submission:
            contest_id = submission.contest_submission.contest_id
            team_id = submission.contest_submission.contest_team.team_id
            contest_team_member_id = (
                submission.contest_submission.contest_team_member_id
            )

        # 2. Update status to RUNNING
        await repository.mark_submission_running(submission)
        await db.commit()

        # 3. Publish RUNNING event
        if contest_id and team_id and contest_team_member_id:
            event = StudentSubmissionUpdateEvent(
                type="submission_update",
                payload=StudentSubmissionUpdatePayload(
                    submission_id=str(submission.id),
                    question_id=str(submission.question_id),
                    status=SubmissionStatus.RUNNING.value,
                ),
            )
            await event_service.publish_event(
                contest_id, team_id, contest_team_member_id, event
            )

        # 4. Get the question and test cases using QuestionRepository
        try:
            question = await repository.get_question_or_raise(submission.question_id)
            template = QuestionValidator.validate_submission_language(
                question, submission.language_id
            )
        except InvalidQuestionError as e:
            logger.error(f"Validation failed for submission: {e}")
            result = EvaluationResult(
                status=SubmissionStatus.SYSTEM_ERROR,
                passed_testcases=0,
                total_testcases=0,
                total_time=0,
                total_memory=0,
                testcase_results=[],
            )
            await repository.complete_submission(submission, result)
            await db.commit()
            if contest_id and team_id and contest_team_member_id:
                event = StudentSubmissionUpdateEvent(
                    type="submission_update",
                    payload=StudentSubmissionUpdatePayload(
                        submission_id=str(submission.id),
                        question_id=str(submission.question_id),
                        status=SubmissionStatus.SYSTEM_ERROR.value,
                    ),
                )
                await event_service.publish_event(
                    contest_id, team_id, contest_team_member_id, event
                )
            return
        except Exception as e:
            logger.error(f"Could not retrieve question for submission: {e}")
            result = EvaluationResult(
                status=SubmissionStatus.SYSTEM_ERROR,
                passed_testcases=0,
                total_testcases=0,
                total_time=0,
                total_memory=0,
                testcase_results=[],
            )
            await repository.complete_submission(submission, result)
            await db.commit()
            if contest_id and team_id and contest_team_member_id:
                event = StudentSubmissionUpdateEvent(
                    type="submission_update",
                    payload=StudentSubmissionUpdatePayload(
                        submission_id=str(submission.id),
                        question_id=str(submission.question_id),
                        status=SubmissionStatus.SYSTEM_ERROR.value,
                    ),
                )
                await event_service.publish_event(
                    contest_id, team_id, contest_team_member_id, event
                )
            return

        testcases = question.testcases
        if not testcases:
            logger.warning(f"No testcases found for question {question.id}")
            result = EvaluationResult(
                status=SubmissionStatus.AC,
                passed_testcases=0,
                total_testcases=0,
                total_time=0,
                total_memory=0,
                testcase_results=[],
            )
            await repository.complete_submission(submission, result)
            await db.commit()
            if contest_id and team_id and contest_team_member_id:
                event = StudentSubmissionUpdateEvent(
                    type="submission_update",
                    payload=StudentSubmissionUpdatePayload(
                        submission_id=str(submission.id),
                        question_id=str(submission.question_id),
                        status=SubmissionStatus.AC.value,
                    ),
                )
                await event_service.publish_event(
                    contest_id, team_id, contest_team_member_id, event
                )
            return

        final_source_code = submission.source_code
        if template and template.driver_code:
            final_source_code = f"{submission.source_code}\n\n{template.driver_code}"

        logger.info(
            f"Fetched question '{question.title}' with {len(testcases)} testcase(s) for submission {submission_id}."
        )

        # 5. Evaluate sequentially
        judge0_repo = Judge0Repository()
        eval_result = await _run_evaluation(
            submission, testcases, judge0_repo, final_source_code
        )

        # 6. Save final results and publish
        await repository.complete_submission(submission, eval_result)
        await db.commit()
        if contest_id and team_id and contest_team_member_id:
            event = StudentSubmissionUpdateEvent(
                type="submission_update",
                payload=StudentSubmissionUpdatePayload(
                    submission_id=str(submission.id),
                    question_id=str(submission.question_id),
                    status=submission.status.value,
                ),
            )
            await event_service.publish_event(
                contest_id, team_id, contest_team_member_id, event
            )

        logger.info(
            f"Finished evaluation for submission {submission.id} with status {submission.status}"
        )


@celery_app.task
def evaluate_submission(submission_id: UUID | str) -> None:
    """Evaluate submission background task."""
    print(f"Evaluating submission: {submission_id}")
    if isinstance(submission_id, str):
        submission_id = UUID(submission_id)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(_evaluate_submission_async(submission_id))
