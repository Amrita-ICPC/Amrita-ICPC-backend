import asyncio
import json
from typing import Sequence
from uuid import UUID

from sqlalchemy import select

from app.core.clients.celery import celery_app
from app.core.clients.database import SessionLocal
from app.core.clients.redis import get_redis
from app.core.logger import logger
from app.exceptions.question import InvalidQuestionError
from app.models.evaluation import Evaluation
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
from app.utils.evaluation import calculate_submission_score
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
                submission=submission,
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
        stc.submission = submission
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


async def _evaluate_submission_core(db: SessionLocal, submission: Submission) -> None:
    """Core logic to evaluate a single submission, scoring it, and saving it, without publishing events."""
    repository = QuestionRepository(db)
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
        submission.score = 0
        await repository.complete_submission(submission, result)
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
        submission.score = 0
        await repository.complete_submission(submission, result)
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
        submission.score = 0
        await repository.complete_submission(submission, result)
        return

    final_source_code = submission.source_code
    if template and template.driver_code:
        final_source_code = f"{submission.source_code}\n\n{template.driver_code}"

    logger.info(
        f"Fetched question '{question.title}' with {len(testcases)} testcase(s) for submission {submission.id}."
    )

    # Evaluate sequentially
    judge0_repo = Judge0Repository()
    eval_result = await _run_evaluation(
        submission, testcases, judge0_repo, final_source_code
    )

    # Save final results
    max_score = 100
    if submission.contest_submission:
        contest_id = submission.contest_submission.contest_id
        contest_question_score = await repository.get_contest_question_score(
            contest_id, submission.question_id
        )
        if contest_question_score is not None:
            max_score = contest_question_score

    submission.score = calculate_submission_score(
        max_score, testcases, eval_result.testcase_results
    )

    await repository.complete_submission(submission, eval_result)


async def _publish_student_submission_event(
    event_service: ContestEventService,
    submission: Submission,
    status: str,
) -> None:
    """Publish submission status update event to the contest event publisher for students."""
    if not submission.contest_submission:
        return
    contest_id = submission.contest_submission.contest_id
    team_id = submission.contest_submission.contest_team.team_id
    contest_team_member_id = submission.contest_submission.contest_team_member_id

    if contest_id and team_id and contest_team_member_id:
        event = StudentSubmissionUpdateEvent(
            type="submission_update",
            payload=StudentSubmissionUpdatePayload(
                submission_id=str(submission.id),
                question_id=str(submission.question_id),
                status=status,
            ),
        )
        await event_service.publish_event(
            contest_id, team_id, contest_team_member_id, event
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

        if submission.is_evaluated:
            logger.warning(
                f"Submission {submission_id} is already evaluated, aborting evaluation."
            )
            return

        logger.info(
            f"Retrieved submission {submission.id} for question {submission.question_id}"
        )

        # 2. Publish RUNNING event
        await _publish_student_submission_event(event_service, submission, "RUNNING")

        # 3. Core evaluation logic
        await _evaluate_submission_core(db, submission)
        await db.commit()

        # 4. Publish completed event
        status_str = submission.status.value if submission.status else "SYSTEM_ERROR"
        await _publish_student_submission_event(event_service, submission, status_str)

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


@celery_app.task
def evaluate_contest_submission(
    evaluation_id: UUID | str, submission_id: UUID | str
) -> None:
    """Evaluate a contest submission and update the evaluation progress."""
    print(
        f"Evaluating contest submission: {submission_id} for evaluation: {evaluation_id}"
    )
    if isinstance(evaluation_id, str):
        evaluation_id = UUID(evaluation_id)
    if isinstance(submission_id, str):
        submission_id = UUID(submission_id)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(
        _evaluate_contest_submission_async(evaluation_id, submission_id)
    )


async def _evaluate_contest_submission_async(
    evaluation_id: UUID, submission_id: UUID
) -> None:
    """Evaluate a contest submission without student event publish and update progress."""
    async with SessionLocal() as db:
        # Check if the evaluation was already completed or marked as evaluated
        result = await db.execute(
            select(Evaluation.is_evaluated).filter(Evaluation.id == evaluation_id)
        )
        is_evaluated = result.scalar_one_or_none()
        if is_evaluated is None or is_evaluated:
            logger.info(
                f"Evaluation {evaluation_id} is already completed/superseded. "
                f"Skipping submission {submission_id}."
            )
            return

        repository = QuestionRepository(db)
        submission = await repository.get_submission(submission_id)
        if submission is None:
            logger.error(f"Submission not found: {submission_id}")
            return

        submission.is_evaluated = False
        await db.commit()

        await _evaluate_submission_core(db, submission)
        await db.commit()

        await _update_progress_db_and_redis(evaluation_id)


async def _update_progress_db_and_redis(
    evaluation_id: UUID,
) -> None:
    """Atomically update DB progress and Redis progress in parallel."""

    async def update_db():
        async with SessionLocal() as db_session:
            result = await db_session.execute(
                select(Evaluation)
                .filter(Evaluation.id == evaluation_id)
                .with_for_update()
            )
            evaluation = result.scalar_one_or_none()
            if not evaluation:
                logger.error(f"Evaluation not found in DB: {evaluation_id}")
                return 0, 0, False

            evaluation.processed_submissions += 1
            if evaluation.processed_submissions >= evaluation.total_submissions:
                evaluation.is_evaluated = True

            processed = evaluation.processed_submissions
            total = evaluation.total_submissions
            is_done = evaluation.is_evaluated

            await db_session.commit()
            return processed, total, is_done

    async def update_redis():
        redis_client = get_redis()
        key = f"evaluation:{evaluation_id}"
        async with redis_client.lock(f"lock:{key}", timeout=5):
            data = await redis_client.get(key)
            if data:
                eval_data = json.loads(data)
                eval_data["processed"] = eval_data.get("processed", 0) + 1
                if eval_data["processed"] >= eval_data.get("total", 0):
                    eval_data["status"] = "COMPLETED"
                else:
                    eval_data["status"] = "RUNNING"
                await redis_client.set(key, json.dumps(eval_data))

    await asyncio.gather(update_db(), update_redis())
