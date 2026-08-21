import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import UUID, uuid4

from fastapi import status
from fastapi.sse import ServerSentEvent
from redis.asyncio import Redis

from app.core.cache import keys as cache_keys
from app.core.cache.decorators import cache_get
from app.core.clients.celery import celery_app
from app.core.clients.database import SessionLocal
from app.core.clients.judge0 import Judge0StatusCode
from app.core.logger import logger
from app.exceptions.auth import PermissionDeniedError
from app.exceptions.base import AppBaseException
from app.exceptions.contest import (
    ContestResultsNotVisibleError,
    QuestionNotInContestError,
)
from app.exceptions.question import QuestionNotFoundError
from app.exceptions.student.contests import (
    ContestSessionEndedError,
    ContestSessionNotStartedError,
    NoContestTeamMemberFoundError,
)
from app.exceptions.submission import SubmissionNotFoundError
from app.models import Contest, ContestSubmission
from app.models.question import Submission
from app.repositories.contest import ContestRepository
from app.repositories.contest_team_progress import ContestTeamProgressRepository
from app.repositories.dto.judge0 import Judge0ExecutionRequestDTO
from app.repositories.judge0 import Judge0Repository
from app.repositories.question import QuestionRepository
from app.repositories.student.contest_question import StudentContestQuestionRepository
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.submission import ContestSubmissionRepository
from app.repositories.testcase import TestCaseRepository
from app.schema.contest import ContestSessionValidationData
from app.schema.student import (
    StudentContestQuestionResponse,
    StudentContestQuestionsListResponse,
    StudentQuestionDetailResponse,
    WorkspaceData,
)
from app.schema.student.run import (
    StudentCodeRunResponse,
    StudentTestCaseRunResultResponse,
)
from app.schema.student.submission import (
    StudentSubmissionDetailResponse,
    StudentSubmissionResponse,
    StudentSubmissionUpdateEvent,
    StudentSubmissionUpdatePayload,
)
from app.schema.submission import (
    SubmissionDetailLanguageSchema,
    SubmissionDetailQuestionSchema,
    SubmissionDetailUserSchema,
)
from app.service.contest_event_service import ContestEventService
from app.service.execution import TestCaseView, get_execution_strategy
from app.service.student.workspace import WorkspaceService
from app.utils.contest import calculate_effective_times
from app.utils.enums import (
    ContestQuestionStatus,
    ContestTeamMemberStatus,
    ContestTeamParticipationType,
    TeamApprovalStatus,
    TeamStatus,
)
from app.utils.key_builder import (
    build_question_view_key,
    build_workspace_key,
    get_contest_channel_key,
)
from app.validators.contest import ContestValidator
from app.validators.contest_team import ContestTeamValidator


class StudentContestQuestionService:
    def __init__(
        self,
        repository: StudentContestQuestionRepository,
        contest_repository: ContestRepository,
        contest_team_repository: ContestTeamRepository,
        contest_team_progress_repository: ContestTeamProgressRepository,
        testcase_repository: TestCaseRepository,
        workspace_service: WorkspaceService,
        judge0_repository: Judge0Repository,
        question_repository: QuestionRepository,
        redis: Redis,
    ):
        self.repository = repository
        self.contest_repository = contest_repository
        self.contest_team_repository = contest_team_repository
        self.contest_team_progress_repository = contest_team_progress_repository
        self.testcase_repository = testcase_repository
        self.workspace_service = workspace_service
        self.judge0_repo = judge0_repository
        self.question_repository = question_repository
        self.redis = redis

    async def _validate_session_and_get_contest(
        self, contest_id: UUID, user_id: UUID
    ) -> ContestSessionValidationData:
        """
        Validate student eligibility, contest runtime status, session progress, and remaining time.
        """
        session_data = await self._get_cached_session_validation_data(
            contest_id=contest_id,
            user_id=user_id,
        )

        # A team/member that explicitly finished their session must not be able
        # to keep submitting/running code just because the raw timer hasn't
        # expired yet.
        if session_data.ended_at is not None:
            raise ContestSessionEndedError()

        # Only the remaining time is intentionally recalculated on every validation.
        _, remaining_seconds = calculate_effective_times(
            base_end_time=session_data.base_end_time,
            extra_time_seconds=session_data.extra_time_seconds,
        )

        if remaining_seconds <= 0:
            raise ContestSessionEndedError()

        return session_data

    @cache_get(
        key_builder=lambda self, contest_id, user_id: (
            cache_keys.student_session_validation_key(contest_id, user_id)
        ),
        ttl=60,
    )
    async def _get_cached_session_validation_data(
        self, contest_id: UUID, user_id: UUID
    ) -> ContestSessionValidationData:
        # 1. Get the contest or raise
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        ContestValidator.validate_contest_is_published(contest.status, contest_id)

        # 2. Get the contest_team_member by accepted status and contest ID
        contest_team_member = (
            await self.contest_team_repository.get_contest_team_member_by_user_id(
                user_id=user_id,
                status=ContestTeamMemberStatus.ACCEPTED,
                team_status=TeamStatus.CONFIRMED,
                approval_status=TeamApprovalStatus.APPROVED,
                contest_id=contest_id,
            )
        )
        if not contest_team_member:
            raise NoContestTeamMemberFoundError()

        # 3. Validate contest team status
        contest_team = contest_team_member.contest_team
        ContestTeamValidator.validate_student_contest_team(contest_team, contest_id)

        # 5. Validate that progress exists (session is started)
        is_individual = (
            contest.participation_type
            == ContestTeamParticipationType.INDIVIDUAL_WORKSPACE
        )
        member_id_filter = contest_team_member.id if is_individual else None

        team_progress = (
            await self.contest_team_progress_repository.get_contest_team_progress_by_id(
                contest_id=contest_id,
                contest_team_id=contest_team.id,
                contest_team_member_id=member_id_filter,
            )
        )
        if team_progress is None:
            raise ContestSessionNotStartedError()

        return ContestSessionValidationData(
            contest_team_id=contest_team.id,
            team_id=contest_team.team_id,
            contest_team_member_id=contest_team_member.id,
            max_submission_per_question=contest.max_submission_per_question,
            evaluate_on_submit=contest.evaluate_on_submit,
            shuffle_questions=contest.shuffle_questions,
            base_end_time=team_progress.end_time,
            extra_time_seconds=team_progress.extra_time_seconds,
            ended_at=team_progress.ended_at,
        )

    async def get_contest_questions(
        self, contest_id: UUID, user_id: UUID
    ) -> StudentContestQuestionsListResponse:
        """
        Get the list of questions for a contest with viewed/submitted/unviewed status.
        Validates eligibility (user is accepted member of confirmed team)
        and if the session is started and live.
        """
        session_data = await self._validate_session_and_get_contest(contest_id, user_id)

        # Retrieve contest questions from repository (in the instructor's
        # canonical order).
        questions = await self.repository.get_contest_questions(contest_id)

        # When shuffle is enabled, present the questions in a per-student
        # randomized order. The order is derived deterministically from the
        # contest and this student's user id, so it is preserved across page
        # refreshes, re-logins, and different devices without any stored state
        # (and survives leaving/rejoining the contest).
        if session_data.shuffle_questions:
            questions = self._shuffle_questions_for_member(
                questions,
                contest_id=contest_id,
                user_id=user_id,
            )

        # Questions with at least one submission from this team (attempted), and
        # whether any of those submissions passed every testcase (solved).
        solved_by_question = await self.repository.get_question_attempt_status(
            contest_id, session_data.contest_team_id
        )

        # Retrieve viewed status per question from Redis
        view_keys = [
            build_question_view_key(
                contest_id, session_data.contest_team_member_id, q.question_id
            )
            for q in questions
        ]
        viewed_flags = await self.redis.mget(view_keys) if view_keys else []
        viewed_question_ids = {
            q.question_id
            for q, flag in zip(questions, viewed_flags)
            if flag is not None
        }

        question_responses = []
        for q in questions:
            is_submitted = q.question_id in solved_by_question
            is_viewed = q.question_id in viewed_question_ids

            if is_submitted:
                status = ContestQuestionStatus.submitted
            elif is_viewed:
                status = ContestQuestionStatus.viewed
            else:
                status = ContestQuestionStatus.unviewed

            question_responses.append(
                StudentContestQuestionResponse(
                    id=q.question_id,
                    title=q.question.title if q.question else "Untitled Question",
                    status=status,
                    max_submission=q.max_submission
                    if q.max_submission is not None
                    else session_data.max_submission_per_question,
                )
            )

        return StudentContestQuestionsListResponse(questions=question_responses)

    async def _validate_results_access(
        self, contest_id: UUID, user_id: UUID
    ) -> tuple[Contest, UUID]:
        """
        Validate that a student may access post-results question review for a
        contest: the contest must have its results published, and the caller
        must have actually participated (an accepted member of a confirmed/
        approved contest team) -- regardless of whether their session is
        still active, ended, or was never started. Deliberately independent
        of `_validate_session_and_get_contest` (the live-session path) so
        that path's validation stays untouched.
        """
        contest = await self.contest_repository.get_contest_or_raise(contest_id)
        ContestValidator.validate_contest_is_published(contest.status, contest_id)

        if not contest.results_published_at:
            raise ContestResultsNotVisibleError(str(contest_id))

        contest_team_member = (
            await self.contest_team_repository.get_contest_team_member_by_user_id(
                user_id=user_id,
                status=ContestTeamMemberStatus.ACCEPTED,
                team_status=TeamStatus.CONFIRMED,
                approval_status=TeamApprovalStatus.APPROVED,
                contest_id=contest_id,
            )
        )
        if not contest_team_member:
            raise NoContestTeamMemberFoundError()

        return contest, contest_team_member.contest_team_id

    async def get_results_questions(
        self, contest_id: UUID, user_id: UUID
    ) -> StudentContestQuestionsListResponse:
        """
        Get the list of questions for a contest for post-results review
        (after results have been published), for students who participated.
        """
        contest, contest_team_id = await self._validate_results_access(
            contest_id, user_id
        )

        questions = await self.repository.get_contest_questions(contest_id)

        solved_by_question = await self.repository.get_question_attempt_status(
            contest_id, contest_team_id
        )

        question_responses = [
            StudentContestQuestionResponse(
                id=q.question_id,
                title=q.question.title if q.question else "Untitled Question",
                status=ContestQuestionStatus.submitted
                if q.question_id in solved_by_question
                else ContestQuestionStatus.unviewed,
                max_submission=q.max_submission
                if q.max_submission is not None
                else contest.max_submission_per_question,
            )
            for q in questions
        ]

        return StudentContestQuestionsListResponse(questions=question_responses)

    async def get_results_question_details(
        self, contest_id: UUID, question_id: UUID, user_id: UUID
    ) -> StudentQuestionDetailResponse:
        """
        Get full details of a question for post-results review (statement,
        testcases, and per-language reference solutions), for students who
        participated in a contest whose results have been published.
        """
        contest, _ = await self._validate_results_access(contest_id, user_id)

        return await self._get_cached_results_question_details(
            contest_id=contest_id,
            question_id=question_id,
            default_max_submission=contest.max_submission_per_question,
        )

    @cache_get(
        key_builder=lambda self, contest_id, question_id, default_max_submission: (
            f"contests:{contest_id}:questions:{question_id}:results"
        ),
        use_lock=True,
    )
    async def _get_cached_results_question_details(
        self,
        contest_id: UUID,
        question_id: UUID,
        default_max_submission: int | None,
    ) -> StudentQuestionDetailResponse:
        in_contest = await self.contest_repository.is_question_in_contest(
            contest_id, question_id
        )
        if not in_contest:
            raise QuestionNotInContestError(str(question_id), str(contest_id))

        question = await self.question_repository.get_question_or_raise(question_id)

        contest_question = await self.contest_repository.get_contest_question(
            contest_id, question_id
        )
        max_sub = contest_question.max_submission if contest_question else None
        if max_sub is None:
            max_sub = default_max_submission

        return StudentQuestionDetailResponse.from_question(
            question, max_submission=max_sub, include_solution=True
        )

    @staticmethod
    def _shuffle_questions_for_member(
        questions: list,
        contest_id: UUID,
        user_id: UUID,
    ) -> list:
        """
        Return the questions in a deterministic, per-student randomized order.

        The order is a stable function of (contest_id, user_id), so the same
        student always sees the same sequence across refreshes, re-logins, and
        different devices, while different students get different orders. Since
        it is keyed on the account (user_id) rather than the membership row, the
        order also survives a student leaving and rejoining the contest. No
        order is persisted -- it is recomputed identically on every request.

        The list is first sorted by the canonical `order` so the shuffle input
        is deterministic regardless of the DB row ordering.
        """
        import random

        ordered = sorted(questions, key=lambda q: q.order)
        seed = f"{contest_id}:{user_id}"
        rng = random.Random(seed)
        rng.shuffle(ordered)
        return ordered

    async def get_contest_question_details(
        self, contest_id: UUID, question_id: UUID, user_id: UUID
    ) -> StudentQuestionDetailResponse:
        """
        Get details of a specific question in a contest.
        Validates student eligibility (session started, runtime active)
        and fetches question preview info (title, statement, limits, languages, tags, public testcases, starter templates).
        """
        session_data = await self._validate_session_and_get_contest(contest_id, user_id)

        # Mark question as viewed in Redis for this student team member
        view_key = build_question_view_key(
            contest_id, session_data.contest_team_member_id, question_id
        )
        await self.redis.set(view_key, "1", ex=60 * 60 * 24 * 30)  # 30 days

        return await self._get_cached_contest_question_details(
            contest_id=contest_id,
            question_id=question_id,
            default_max_submission=session_data.max_submission_per_question,
        )

    @cache_get(
        key_builder=lambda self, contest_id, question_id, default_max_submission: (
            f"contests:{contest_id}:questions:{question_id}"
        ),
        use_lock=True,
    )
    async def _get_cached_contest_question_details(
        self,
        contest_id: UUID,
        question_id: UUID,
        default_max_submission: int | None,
    ) -> StudentQuestionDetailResponse:
        # Retrieve contest question details from repository
        question = await self.repository.get_contest_question_details(
            contest_id, question_id
        )
        if not question:
            raise QuestionNotInContestError(str(question_id), str(contest_id))

        contest_question = await self.contest_repository.get_contest_question(
            contest_id, question_id
        )
        max_sub = contest_question.max_submission if contest_question else None
        if max_sub is None:
            max_sub = default_max_submission

        # Map to response schema
        return StudentQuestionDetailResponse.from_question(
            question, max_submission=max_sub
        )

    async def _get_workspace_key_and_validate(
        self, contest_id: UUID, question_id: UUID, user_id: UUID
    ) -> str:
        """
        Validate student eligibility and contest runtime status, then build the redis workspace key.
        """
        session_data = await self._validate_session_and_get_contest(contest_id, user_id)

        # Verify that the question exists in the contest
        in_contest = await self.contest_repository.is_question_in_contest(
            contest_id, question_id
        )
        if not in_contest:
            raise QuestionNotInContestError(str(question_id), str(contest_id))

        return build_workspace_key(
            contest_id=contest_id,
            question_id=question_id,
            contest_team_member_id=session_data.contest_team_member_id,
        )

    async def get_workspace(
        self, contest_id: UUID, question_id: UUID, user_id: UUID
    ) -> WorkspaceData | None:
        """
        Get the saved workspace code for the student/team.
        """
        key = await self._get_workspace_key_and_validate(
            contest_id, question_id, user_id
        )
        return await self.workspace_service.get_workspace(key)

    async def save_workspace(
        self,
        contest_id: UUID,
        question_id: UUID,
        user_id: UUID,
        language_id: int,
        source_code: str,
    ) -> None:
        """
        Save the workspace code for the student/team.
        """
        key = await self._get_workspace_key_and_validate(
            contest_id, question_id, user_id
        )
        await self.workspace_service.save_workspace(
            key=key,
            language_id=language_id,
            source_code=source_code,
        )

    async def run_code(
        self,
        contest_id: UUID,
        question_id: UUID,
        user_id: UUID,
        code: str,
        language_id: int,
    ) -> StudentCodeRunResponse:
        """
        Execute student code against all non-hidden test cases of the question.
        Uses a temporary DB session to fetch details and closes it before Judge0 execution/polling.
        """
        import asyncio

        async with SessionLocal() as db:
            temp_service = StudentContestQuestionService(
                repository=StudentContestQuestionRepository(db),
                contest_repository=ContestRepository(db),
                contest_team_repository=ContestTeamRepository(db),
                contest_team_progress_repository=ContestTeamProgressRepository(db),
                testcase_repository=TestCaseRepository(db),
                workspace_service=WorkspaceService(self.redis),
                judge0_repository=Judge0Repository(),
                question_repository=QuestionRepository(db),
                redis=self.redis,
            )

            # Validate student eligibility, contest runtime status, session progress, and remaining time.
            await temp_service._validate_session_and_get_contest(contest_id, user_id)

            # Retrieve contest question details (includes templates and language mappings)
            question = await temp_service.repository.get_contest_question_details(
                contest_id, question_id
            )
            if not question:
                raise QuestionNotInContestError(str(question_id), str(contest_id))

            # Retrieve public (non-hidden) test cases
            non_hidden = (
                await temp_service.testcase_repository.get_non_hidden_by_question(
                    question_id
                )
            )
            if not non_hidden:
                raise QuestionNotFoundError(
                    f"No non-hidden test case found for question {question_id}"
                )

            question_type = question.question_type

            # Retrieve driver code from template if available
            driver_code = ""
            for template in question.templates:
                if template.language_id == language_id:
                    driver_code = template.driver_code or ""
                    break

            testcases_data = [
                (tc.id, tc.input, tc.output, tc.is_ordered) for tc in non_hidden
            ]

        # DB connection is now closed before calling Judge0!
        full_source_code = code
        if driver_code:
            full_source_code = f"{code}\n\n{driver_code}"

        logger.info(
            f"Running code for user {user_id} on question {question_id} in contest {contest_id} "
            f"against {len(testcases_data)} test cases"
        )

        # Build Judge0 request DTO with full source code (solution + driver)
        judge0_request = Judge0ExecutionRequestDTO(
            question_id=str(question_id),
            source_code=full_source_code,
            language_id=language_id,
        )
        strategy = get_execution_strategy(
            question_type=question_type,
            language_id=language_id,
        )

        judge0_repo = (
            self.judge0_repo
            if hasattr(self, "judge0_repo") and self.judge0_repo
            else Judge0Repository()
        )

        # Submit code to Judge0 for all testcases in parallel
        submit_tasks = [
            judge0_repo.submit_code(
                *strategy.build_submission(
                    judge0_request,
                    TestCaseView(
                        input=tc_input, output=tc_output, is_ordered=tc_is_ordered
                    ),
                )
            )
            for _, tc_input, tc_output, tc_is_ordered in testcases_data
        ]
        submissions = await asyncio.gather(*submit_tasks)

        # Wait for all submissions in parallel
        wait_tasks = [judge0_repo.wait_for_completion(sub.token) for sub in submissions]
        judge0_results = await asyncio.gather(*wait_tasks)

        # Map results to Schema models
        results = []
        for (tc_id, tc_input, tc_output, tc_is_ordered), judge0_result in zip(
            testcases_data, judge0_results
        ):
            testcase_view = TestCaseView(
                input=tc_input,
                output=tc_output,
                is_ordered=tc_is_ordered,
            )
            judge0_ok = judge0_result.status_id == Judge0StatusCode.ACCEPTED.value
            passed = strategy.passed(
                judge0_accepted=judge0_ok,
                stdout=judge0_result.stdout,
                testcase=testcase_view,
            )
            # Judge0 reports ACCEPTED whenever a SQL query ran without error
            # since no expected_output is sent for it -- the strategy's own
            # comparison is what actually decides pass/fail for SQL.
            status_description = (
                "WRONG_ANSWER"
                if judge0_ok and not passed
                else (judge0_result.status.name if judge0_result.status else "Unknown")
            )

            results.append(
                StudentTestCaseRunResultResponse(
                    testcase_id=tc_id,
                    passed=passed,
                    status_description=status_description,
                    time=judge0_result.time or 0.0,
                    memory=(judge0_result.memory or 0) / 1024,
                    stdout=judge0_result.stdout,
                    stderr=strategy.redact(judge0_result.stderr, testcase_view),
                    compile_output=strategy.redact(
                        judge0_result.compile_output, testcase_view
                    ),
                    expected_output=tc_output,
                    input=strategy.visible_input(testcase_view),
                )
            )

        overall_passed = all(r.passed for r in results)

        return StudentCodeRunResponse(
            passed=overall_passed,
            results=results,
            message="Code executed successfully",
            question_id=question_id,
        )

    async def submit_code(
        self,
        contest_id: UUID,
        question_id: UUID,
        user_id: UUID,
        code: str,
        language_id: int,
    ) -> StudentSubmissionResponse:
        """
        Submit student code for a question in a contest.

        Validates session status, eligibility, and question existence, then stores a new submission.

        Args:
            contest_id: ID of the contest.
            question_id: ID of the question.
            user_id: ID of the student.
            code: Source code to submit.
            language_id: Language ID of the code.

        Returns:
            StudentSubmissionResponse: The created submission details.
        """
        # Validate student eligibility, contest runtime status, session progress, and remaining time.
        session_data = await self._validate_session_and_get_contest(
            contest_id=contest_id, user_id=user_id
        )

        # Verify that the question exists in the contest and retrieve it
        contest_question = await self.contest_repository.get_contest_question(
            contest_id, question_id
        )
        if not contest_question:
            raise QuestionNotInContestError(str(question_id), str(contest_id))

        # Serialize the count-then-insert submission check below against any
        # other concurrent submit from this same member for this question
        # (see acquire_submission_slot_lock docstring for why a plain DB
        # constraint can't express this dynamic, cross-table limit).
        await self.repository.acquire_submission_slot_lock(
            contest_id, session_data.contest_team_member_id, question_id
        )

        existing_submissions = (
            await self.repository.get_submissions_by_team_and_question(
                session_data.contest_team_id, question_id
            )
        )

        # Check max_submission limits
        max_sub = contest_question.max_submission
        if max_sub is None:
            max_sub = session_data.max_submission_per_question

        if max_sub is not None:
            if len(existing_submissions) >= max_sub:
                raise AppBaseException(
                    message=f"Maximum submissions ({max_sub}) reached for this question.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        # Retrieve test cases to count total test cases
        testcases = await self.testcase_repository.get_all_by_question(question_id)

        # Create submission record
        submission = Submission(
            id=uuid4(),
            question_id=question_id,
            source_code=code,
            language_id=language_id,
            is_evaluated=False,
            score=0,
            created_at=datetime.now(timezone.utc),
        )
        submission.passed_testcases = 0
        submission.total_testcases = len(testcases)

        # Create contest submission mapping
        contest_submission = ContestSubmission(
            submission=submission,
            contest_id=contest_id,
            contest_team_id=session_data.contest_team_id,
            contest_team_member_id=session_data.contest_team_member_id,
        )

        # Save to postgres
        await self.question_repository.create_submission(
            submission=submission, contest_submission=contest_submission
        )

        # Commit the transaction before dispatching the Celery task.
        # The `get_db` dependency auto-commits only after the route handler returns,
        # which is after send_task(). Without an explicit commit here the worker
        # picks up the task and queries the DB before the row is visible,
        # causing "Submission not found" errors.
        await self.question_repository.db.commit()

        # Trigger background evaluation task via Celery only if evaluate_on_submit is True
        if session_data.evaluate_on_submit:
            # SUBMIT stage on the interactive queue. No contest_id/evaluation_id
            # here -> live student submission (not a bulk re-evaluation run).
            celery_app.send_task(
                "worker.evaluation.submit_evaluation",
                kwargs={
                    "submission_id": str(submission.id),
                    "reevaluation": False,
                    "publish_events": True,
                },
                queue="student_submit",
            )
            try:
                team_id = session_data.team_id
                contest_team_member_id = session_data.contest_team_member_id

                if team_id is not None:
                    event_service = ContestEventService()
                    event = StudentSubmissionUpdateEvent(
                        type="submission_update",
                        payload=StudentSubmissionUpdatePayload(
                            submission_id=str(submission.id),
                            question_id=str(submission.question_id),
                            status="RUNNING",
                        ),
                    )
                    await event_service.publish_event(
                        contest_id=contest_id,
                        team_id=team_id,
                        contest_team_member_id=contest_team_member_id,
                        event=event,
                    )
            except Exception as e:
                logger.error(f"Failed to publish initial RUNNING event: {e}")

        return StudentSubmissionResponse.model_validate(submission)

    async def get_question_submissions(
        self, contest_id: UUID, question_id: UUID, user_id: UUID
    ) -> list[StudentSubmissionResponse]:
        """
        Retrieve all submissions for a question made by the student's team.
        """
        session_data = await self._validate_session_and_get_contest(
            contest_id=contest_id, user_id=user_id
        )

        in_contest = await self.contest_repository.is_question_in_contest(
            contest_id, question_id
        )
        if not in_contest:
            raise QuestionNotInContestError(str(question_id), str(contest_id))

        submissions = await self.repository.get_submissions_by_team_and_question(
            session_data.contest_team_id, question_id
        )

        return [StudentSubmissionResponse.model_validate(sub) for sub in submissions]

    @staticmethod
    async def subscribe_submission_events(
        contest_id: UUID, user_id: UUID, redis_client: Redis
    ) -> AsyncGenerator[ServerSentEvent, None]:
        """
        Subscribe to submission progress/status updates via Redis pubsub and yield them.
        """
        async with SessionLocal() as db:
            service = StudentContestQuestionService(
                repository=StudentContestQuestionRepository(db),
                contest_repository=ContestRepository(db),
                contest_team_repository=ContestTeamRepository(db),
                contest_team_progress_repository=ContestTeamProgressRepository(db),
                testcase_repository=TestCaseRepository(db),
                workspace_service=WorkspaceService(redis_client),
                judge0_repository=Judge0Repository(),
                question_repository=QuestionRepository(db),
                redis=redis_client,
            )
            # Validate student eligibility, contest runtime status, session progress, and remaining time.
            session_data = await service._validate_session_and_get_contest(
                contest_id=contest_id, user_id=user_id
            )

        pubsub = redis_client.pubsub()
        channel = get_contest_channel_key(
            contest_id,
            session_data.team_id,
            session_data.contest_team_member_id,
        )

        try:
            await pubsub.subscribe(channel)
            logger.info(f"Subscribed to {channel}")
            yield ServerSentEvent(comment="stream of contest lifecycle updates")

            while True:
                _, remaining_seconds = calculate_effective_times(
                    base_end_time=session_data.base_end_time,
                    extra_time_seconds=session_data.extra_time_seconds,
                )
                if remaining_seconds <= 0:
                    logger.info(
                        f"Contest session ended for user {user_id} in contest {contest_id}, closing stream."
                    )
                    break

                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=15.0
                )
                if message:
                    if message["type"] == "message":
                        data = message["data"]
                        if isinstance(data, bytes):
                            data = data.decode("utf-8")
                        logger.info(
                            f"SSE event message received on channel {channel}: {data}"
                        )
                        try:
                            event_dict = json.loads(data)
                            event_type = event_dict.get("type", "message")
                            yield ServerSentEvent(
                                data=data,
                                event=event_type,
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to parse SSE event from message data: {e}"
                            )
        except asyncio.CancelledError:
            logger.info("SSE client disconnected")
            raise
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    async def get_submission_detail(
        self, contest_id: UUID, submission_id: UUID, user_id: UUID
    ) -> StudentSubmissionDetailResponse:
        """
        Retrieve details of a submission if it belongs to the student's team.

        Args:
            contest_id: UUID of the contest.
            submission_id: UUID of the submission.
            user_id: UUID of the requesting student.

        Returns:
            StudentSubmissionDetailResponse: Details of the submission.

        Raises:
            SubmissionNotFoundError: If the submission is not found.
            PermissionDeniedError: If the student does not have access.
        """
        # 1. Verify student is a member of a team in this contest
        contest_team_member = (
            await self.contest_team_repository.get_contest_team_member_by_user_id(
                user_id=user_id,
                status=ContestTeamMemberStatus.ACCEPTED,
                team_status=TeamStatus.CONFIRMED,
                approval_status=TeamApprovalStatus.APPROVED,
                contest_id=contest_id,
            )
        )
        if not contest_team_member:
            raise NoContestTeamMemberFoundError()

        # 2. Retrieve submission using repository method
        submission = await self.question_repository.get_submission(submission_id)
        if not submission:
            raise SubmissionNotFoundError(submission_id)

        contest_sub = submission.contest_submission
        if not contest_sub:
            raise SubmissionNotFoundError(submission_id)

        # 3. Verify submission belongs to the contest and the student's team
        if (
            contest_sub.contest_id != contest_id
            or contest_sub.contest_team_id != contest_team_member.contest_team_id
        ):
            raise PermissionDeniedError(
                "You do not have permission to view this submission."
            )

        # 4. Fetch submission details
        submission_repo = ContestSubmissionRepository(self.repository.db)
        row = await submission_repo.get_submission_detail(submission_id)

        # 5. Map to StudentSubmissionDetailResponse
        return StudentSubmissionDetailResponse(
            submission_id=row.submission_id,
            question=SubmissionDetailQuestionSchema(
                id=row.question_id,
                title=row.question_title,
            ),
            submitted_by=SubmissionDetailUserSchema(
                id=row.submitted_by_id,
                name=row.submitted_by_name,
            ),
            status=row.status,
            score=row.score,
            language=SubmissionDetailLanguageSchema(
                id=row.language_id,
                name=row.language_name,
            ),
            submitted_at=row.submitted_at,
            execution_time_ms=row.execution_time_ms,
            memory_kb=row.memory_kb,
            passed_testcases=int(row.passed_testcases or 0),
            total_testcases=int(row.total_testcases or 0),
            source_code=row.source_code,
        )
