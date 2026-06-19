from typing import TypedDict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clients.database import SessionLocal
from app.core.logger import logger
from app.models.contest import ContestSubmission, ContestTeam
from app.models.question import Submission, SubmissionTestCase
from app.repositories.dto.evaluation import EvaluationResult
from app.repositories.question import QuestionRepository
from app.schema.evaluation import ContestSubmissionContext, EvaluationPreparationDetails
from app.schema.question import (
    QuestionAndTestcasesResponse,
    QuestionTestCaseResponse,
)
from app.service.contest_event_service import ContestEventService
from app.utils.enums import SubmissionStatus
from app.utils.evaluation import calculate_submission_score
from app.validators.question import QuestionValidator
from worker.judge0_service import Judge0EvaluationService
from worker.redis_helper import is_evaluation_valid, update_evaluation_progress


class EvaluationContext(TypedDict):
    contest_id: UUID
    evaluation_id: UUID


class EvaluationService:
    """Service to manage the fetching, execution orchestration, and saving of submission evaluations."""

    def __init__(self) -> None:
        self.judge0_service = Judge0EvaluationService()

    async def _get_contest_submission_context(
        self, db: AsyncSession, submission_id: UUID
    ) -> ContestSubmissionContext | None:
        """Fetch the contest submission context via a direct SELECT, avoiding ORM lazy-loading.

        Args:
            db: The async database session.
            submission_id: UUID of the submission to look up.

        Returns:
            ContestSubmissionContext if the submission belongs to a contest, otherwise None.
        """
        stmt = (
            select(
                ContestSubmission.contest_id,
                ContestSubmission.contest_team_member_id,
                ContestTeam.team_id,
            )
            .join(ContestTeam, ContestTeam.id == ContestSubmission.contest_team_id)
            .where(ContestSubmission.submission_id == submission_id)
        )
        res = await db.execute(stmt)
        row = res.first()
        if row:
            return ContestSubmissionContext(
                contest_id=row.contest_id,
                team_id=row.team_id,
                contest_team_member_id=row.contest_team_member_id,
            )
        return None

    async def get_question_and_testcases(
        self, db: AsyncSession, question_id: UUID
    ) -> QuestionAndTestcasesResponse:
        """
        Fetch the question and its associated testcases from the database.

        Args:
            db: AsyncSession database session.
            question_id: UUID of the question to retrieve.

        Returns:
            QuestionAndTestcasesResponse: A Pydantic model containing the question,
                                          testcases, and templates for evaluation.
        """
        repository = QuestionRepository(db)
        question = await repository.get_question_or_raise(question_id)
        return QuestionAndTestcasesResponse.from_question_and_testcases(
            question, list(question.testcases)
        )

    async def cleanup_submission(
        self,
        db: AsyncSession,
        repository: QuestionRepository,
        submission_id: UUID,
        submission: Submission,
    ) -> None:
        """Reset evaluation status and clean up old testcase results from the database."""
        submission.is_evaluated = False
        testcase_exists_result = await db.execute(
            select(SubmissionTestCase.id)
            .filter(SubmissionTestCase.submission_id == submission_id)
            .limit(1)
        )
        has_testcases = testcase_exists_result.scalar_one_or_none() is not None

        if has_testcases:
            await repository.delete_submission_testcases_batch(submission_id)

        await db.commit()

    async def prepare_evaluation(
        self,
        db: AsyncSession,
        submission_id: UUID,
        reevaluation: bool = False,
    ) -> EvaluationPreparationDetails | None:
        """
        Prepare details for submission evaluation.

        Args:
            db: AsyncSession database session.
            submission_id: UUID of the submission to evaluate.
            reevaluation: If True, resets evaluated status and deletes old testcase results.
                          If False, aborts if the submission has already been evaluated.

        Returns:
            EvaluationPreparationDetails: Pydantic model containing the submission, testcases,
                                          source code, and context, or None if aborted.
        """
        repository = QuestionRepository(db)

        # 1. Fetch submission
        submission = await repository.get_submission(submission_id)
        if submission is None:
            logger.error(f"Submission not found: {submission_id}")
            return None

        if reevaluation:
            await self.cleanup_submission(db, repository, submission_id, submission)
        else:
            # Ensure it hasn't been evaluated already
            if submission.is_evaluated:
                logger.warning(
                    f"Submission {submission_id} is already evaluated, aborting evaluation."
                )
                return None

        # Build context for SSE updates
        contest_submission_context = await self._get_contest_submission_context(
            db, submission_id
        )

        # 2. Fetch question and testcases
        data = await self.get_question_and_testcases(db, submission.question_id)
        testcases = data.testcases

        template = QuestionValidator.validate_submission_language(
            data, submission.language_id
        )

        if not testcases:
            logger.warning(f"No testcases found for question {data.id}")
            return EvaluationPreparationDetails(
                submission=submission,
                testcases=[],
                final_source_code="",
                max_score=0,
                contest_submission_context=contest_submission_context,
            )

        # 3. Form final source code
        final_source_code = submission.source_code
        if template and template.driver_code:
            final_source_code = f"{submission.source_code}\n\n{template.driver_code}"

        # 4. Get max score
        max_score = 100
        if contest_submission_context:
            contest_id = contest_submission_context.contest_id
            contest_question_score = await repository.get_contest_question_score(
                contest_id, submission.question_id
            )
            if contest_question_score is not None:
                max_score = contest_question_score

        return EvaluationPreparationDetails(
            submission=submission,
            testcases=testcases,
            final_source_code=final_source_code,
            max_score=max_score,
            contest_submission_context=contest_submission_context,
        )

    async def save_result(
        self,
        db: AsyncSession,
        submission_id: UUID,
        eval_result: EvaluationResult,
        testcases: list[QuestionTestCaseResponse],
        max_score: int,
    ) -> Submission | None:
        """Save evaluation result in database."""
        score = calculate_submission_score(
            max_score, testcases, eval_result.testcase_results
        )

        repository = QuestionRepository(db)
        submission = await repository.get_submission(submission_id)
        if submission is None:
            logger.error(f"Submission not found during save phase: {submission_id}")
            return None

        # Re-associate the testcase result objects with the fresh session's submission
        for stc in eval_result.testcase_results:
            stc.submission = submission
            stc.submission_id = submission.id

        submission.score = score
        await repository.complete_submission(submission, eval_result)
        await db.commit()
        return submission

    async def _publish_student_event(
        self,
        event_service: ContestEventService,
        submission_id: UUID,
        question_id: UUID,
        contest_submission_context: ContestSubmissionContext | None,
        status: str,
    ) -> None:
        """Publish submission status update event to the contest event publisher for students."""
        if not contest_submission_context:
            return
        contest_id = contest_submission_context.contest_id
        team_id = contest_submission_context.team_id
        contest_team_member_id = contest_submission_context.contest_team_member_id
        if contest_id and team_id and contest_team_member_id:
            from app.schema.student.submission import (
                StudentSubmissionUpdateEvent,
                StudentSubmissionUpdatePayload,
            )

            event = StudentSubmissionUpdateEvent(
                type="submission_update",
                payload=StudentSubmissionUpdatePayload(
                    submission_id=str(submission_id),
                    question_id=str(question_id),
                    status=status,
                ),
            )
            await event_service.publish_event(
                contest_id, team_id, contest_team_member_id, event
            )

    async def evaluate(
        self,
        submission_id: UUID,
        reevaluation: bool = False,
        publish_events: bool = True,
        evaluation_context: EvaluationContext | None = None,
    ) -> None:
        """Unifies evaluation and re-evaluation paths for student and instructor submissions."""
        event_service = ContestEventService()
        contest_id = None
        evaluation_id = None

        if evaluation_context:
            contest_id = evaluation_context.get("contest_id")
            evaluation_id = evaluation_context.get("evaluation_id")

        # Step 1: Redis validity check if contest context is present
        if contest_id and evaluation_id:
            if not await is_evaluation_valid(contest_id, evaluation_id, submission_id):
                return

        # Step 2: Phase 1: DB Load, Validation, and Option Setup
        async with SessionLocal() as db:
            try:
                prep = await self.prepare_evaluation(
                    db, submission_id, reevaluation=reevaluation
                )
                if prep is None:
                    if contest_id and evaluation_id:
                        await update_evaluation_progress(contest_id, evaluation_id)
                    return
                submission = prep.submission
                testcases = prep.testcases
                final_source_code = prep.final_source_code
                max_score = prep.max_score
                contest_submission_context = prep.contest_submission_context
                question_id = submission.question_id
                language_id = submission.language_id
            except Exception as e:
                logger.error(
                    f"Validation/load failed for submission {submission_id}: {e}"
                )
                try:
                    await db.rollback()
                except Exception:
                    pass

                async with SessionLocal() as fresh_db:
                    repository = QuestionRepository(fresh_db)
                    sub = await repository.get_submission(submission_id)
                    if sub:
                        result = EvaluationResult(
                            status=SubmissionStatus.SYSTEM_ERROR,
                            passed_testcases=0,
                            total_testcases=0,
                            total_time=0,
                            total_memory=0,
                            testcase_results=[],
                        )
                        sub.score = 0
                        await repository.complete_submission(sub, result)
                        await fresh_db.commit()

                        if publish_events:
                            contest_sub_ctx = (
                                await self._get_contest_submission_context(
                                    fresh_db, submission_id
                                )
                            )
                            await self._publish_student_event(
                                event_service,
                                submission_id,
                                sub.question_id,
                                contest_sub_ctx,
                                "SYSTEM_ERROR",
                            )
                    if contest_id and evaluation_id:
                        await update_evaluation_progress(contest_id, evaluation_id)
                    return

            # Publish RUNNING event
            if publish_events:
                await self._publish_student_event(
                    event_service,
                    submission_id,
                    question_id,
                    contest_submission_context,
                    "RUNNING",
                )

            if not testcases:
                repository = QuestionRepository(db)
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
                await db.commit()

                if publish_events:
                    await self._publish_student_event(
                        event_service,
                        submission_id,
                        question_id,
                        contest_submission_context,
                        "AC",
                    )
                if contest_id and evaluation_id:
                    await update_evaluation_progress(contest_id, evaluation_id)
                return

        # Phase 2: Run evaluation (No database session held)
        eval_result = await self.judge0_service.run_evaluation(
            submission_id, question_id, language_id, testcases, final_source_code
        )

        # Phase 3: Save results
        async with SessionLocal() as db:
            # Check again if the evaluation was completed/superseded during Phase 2
            if contest_id and evaluation_id:
                if not await is_evaluation_valid(
                    contest_id, evaluation_id, submission_id
                ):
                    return

            saved_submission = await self.save_result(
                db, submission_id, eval_result, testcases, max_score
            )
            if saved_submission is None:
                return

            status_str = (
                eval_result.status.value if eval_result.status else "SYSTEM_ERROR"
            )
            if publish_events:
                await self._publish_student_event(
                    event_service,
                    submission_id,
                    question_id,
                    contest_submission_context,
                    status_str,
                )

            logger.info(
                f"Finished evaluation for submission {submission_id} with status {status_str}"
            )

        if contest_id and evaluation_id:
            await update_evaluation_progress(contest_id, evaluation_id)
