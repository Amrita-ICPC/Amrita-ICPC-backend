import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import UUID, uuid4

from fastapi.sse import ServerSentEvent
from redis.asyncio import Redis

from app.core.clients.celery import celery_app
from app.core.logger import logger
from app.exceptions.contest import (
    QuestionNotInContestError,
)
from app.exceptions.question import QuestionNotFoundError
from app.exceptions.student.contests import (
    ContestSessionEndedError,
    ContestSessionNotStartedError,
    NoContestTeamMemberFoundError,
)
from app.models import Contest, ContestSubmission, ContestTeam, ContestTeamMember
from app.models.question import Submission
from app.repositories.contest import ContestRepository
from app.repositories.contest_team_progress import ContestTeamProgressRepository
from app.repositories.dto.judge0 import Judge0ExecutionRequestDTO
from app.repositories.judge0 import Judge0Repository
from app.repositories.question import QuestionRepository
from app.repositories.student.contest_question import StudentContestQuestionRepository
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.testcase import TestCaseRepository
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
    StudentSubmissionResponse,
)
from app.service.student.workspace import WorkspaceService
from app.utils.contest import calculate_effective_times
from app.utils.enums import (
    ContestTeamMemberStatus,
    ContestTeamParticipationType,
    SubmissionStatus,
    TeamApprovalStatus,
    TeamStatus,
)
from app.utils.key_builder import build_workspace_key, get_contest_channel_key
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
    ) -> tuple[Contest, ContestTeam, ContestTeamMember]:
        """
        Validate student eligibility, contest runtime status, session progress, and remaining time.
        """
        # 1. Get the contest or raise
        contest = await self.contest_repository.get_contest_or_raise(contest_id)

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

        # 6. Validate session expiration (remaining seconds > 0)
        base_end_time = team_progress.end_time

        _, remaining_seconds = calculate_effective_times(
            base_end_time=base_end_time,
            extra_time_seconds=team_progress.extra_time_seconds,
        )

        if remaining_seconds <= 0:
            raise ContestSessionEndedError()

        return contest, contest_team, contest_team_member

    async def get_contest_questions(
        self, contest_id: UUID, user_id: UUID
    ) -> StudentContestQuestionsListResponse:
        """
        Get the list of questions for a contest with attempted/solved status.
        Validates eligibility (user is accepted member of confirmed team)
        and if the session is started and live.
        """
        await self._validate_session_and_get_contest(contest_id, user_id)

        # Retrieve contest questions from repository
        questions = await self.repository.get_contest_questions(contest_id)

        # Map to response schema (attempted and solved flags default to False for now)
        question_responses = [
            StudentContestQuestionResponse(
                id=q.question_id,
                attempted=False,
                solved=False,
            )
            for q in questions
        ]

        return StudentContestQuestionsListResponse(questions=question_responses)

    async def get_contest_question_details(
        self, contest_id: UUID, question_id: UUID, user_id: UUID
    ) -> StudentQuestionDetailResponse:
        """
        Get details of a specific question in a contest.
        Validates student eligibility (session started, runtime active)
        and fetches question preview info (title, statement, limits, languages, tags, public testcases, starter templates).
        """
        await self._validate_session_and_get_contest(contest_id, user_id)

        # Retrieve contest question details from repository
        question = await self.repository.get_contest_question_details(
            contest_id, question_id
        )
        if not question:
            raise QuestionNotInContestError(str(question_id), str(contest_id))

        # Map to response schema
        return StudentQuestionDetailResponse.from_question(question)

    async def _get_workspace_key_and_validate(
        self, contest_id: UUID, question_id: UUID, user_id: UUID
    ) -> str:
        """
        Validate student eligibility and contest runtime status, then build the redis workspace key.
        """
        (
            contest,
            contest_team,
            contest_team_member,
        ) = await self._validate_session_and_get_contest(contest_id, user_id)

        # Verify that the question exists in the contest
        in_contest = await self.contest_repository.is_question_in_contest(
            contest_id, question_id
        )
        if not in_contest:
            raise QuestionNotInContestError(str(question_id), str(contest_id))

        return build_workspace_key(
            contest_id=contest_id,
            question_id=question_id,
            contest_team_member_id=contest_team_member.id,
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
        """
        import asyncio

        # Validate student eligibility, contest runtime status, session progress, and remaining time.
        await self._validate_session_and_get_contest(contest_id, user_id)

        # Retrieve contest question details (includes templates and language mappings)
        question = await self.repository.get_contest_question_details(
            contest_id, question_id
        )
        if not question:
            raise QuestionNotInContestError(str(question_id), str(contest_id))

        # Retrieve public (non-hidden) test cases
        non_hidden = await self.testcase_repository.get_non_hidden_by_question(
            question_id
        )
        if not non_hidden:
            raise QuestionNotFoundError(
                f"No non-hidden test case found for question {question_id}"
            )

        # Retrieve driver code from template if available
        driver_code = ""
        for template in question.templates:
            if template.language_id == language_id:
                driver_code = template.driver_code or ""
                break

        full_source_code = code
        if driver_code:
            full_source_code = f"{code}\n\n{driver_code}"

        logger.info(
            f"Running code for user {user_id} on question {question_id} in contest {contest_id} "
            f"against {len(non_hidden)} test cases"
        )

        # Build Judge0 request DTO with full source code (solution + driver)
        judge0_request = Judge0ExecutionRequestDTO(
            question_id=str(question_id),
            source_code=full_source_code,
            language_id=language_id,
        )

        # Submit code to Judge0 for all testcases in parallel
        submit_tasks = [
            self.judge0_repo.submit_code(judge0_request, tc.input, tc.output)
            for tc in non_hidden
        ]
        submissions = await asyncio.gather(*submit_tasks)

        # Wait for all submissions in parallel
        wait_tasks = [
            self.judge0_repo.wait_for_completion(sub.token) for sub in submissions
        ]
        judge0_results = await asyncio.gather(*wait_tasks)

        # Map results to Schema models
        results = []
        for testcase, judge0_result in zip(non_hidden, judge0_results):
            status_id = judge0_result.status_id or 0
            # Code run passed only if execution succeeded (status_id == 3 is ACCEPTED)
            passed = status_id == 3

            results.append(
                StudentTestCaseRunResultResponse(
                    testcase_id=testcase.id,
                    passed=passed,
                    status_description=judge0_result.status.name
                    if judge0_result.status
                    else "Unknown",
                    time=judge0_result.time or 0.0,
                    memory=judge0_result.memory or 0.0,
                    stdout=judge0_result.stdout,
                    stderr=judge0_result.stderr,
                    compile_output=judge0_result.compile_output,
                    expected_output=testcase.output,
                    input=testcase.input,
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
        (
            _,
            contest_team,
            contest_team_member,
        ) = await self._validate_session_and_get_contest(
            contest_id=contest_id, user_id=user_id
        )

        # Verify that the question exists in the contest
        in_contest = await self.contest_repository.is_question_in_contest(
            contest_id, question_id
        )
        if not in_contest:
            raise QuestionNotInContestError(str(question_id), str(contest_id))

        # Retrieve test cases to count total test cases
        testcases = await self.testcase_repository.get_all_by_question(question_id)

        # Create submission record
        submission = Submission(
            id=uuid4(),
            question_id=question_id,
            source_code=code,
            language_id=language_id,
            status=SubmissionStatus.QUEUED,
            score=0,
            passed_testcases=0,
            total_testcases=len(testcases),
            created_at=datetime.now(timezone.utc),
        )

        # Create contest submission mapping
        contest_submission = ContestSubmission(
            submission=submission,
            contest_id=contest_id,
            contest_team_id=contest_team.id,
            contest_team_member_id=contest_team_member.id,
        )

        # Save to postgres
        await self.question_repository.create_submission(
            submission=submission, contest_submission=contest_submission
        )

        # Trigger background evaluation task via Celery
        celery_app.send_task(
            "worker.evaluation.evaluate_submission",
            args=[str(submission.id)],
        )

        return StudentSubmissionResponse.model_validate(submission)

    async def get_question_submissions(
        self, contest_id: UUID, question_id: UUID, user_id: UUID
    ) -> list[StudentSubmissionResponse]:
        """
        Retrieve all submissions for a question made by the student's team.
        """
        (
            contest,
            contest_team,
            contest_team_member,
        ) = await self._validate_session_and_get_contest(
            contest_id=contest_id, user_id=user_id
        )

        in_contest = await self.contest_repository.is_question_in_contest(
            contest_id, question_id
        )
        if not in_contest:
            raise QuestionNotInContestError(str(question_id), str(contest_id))

        submissions = await self.repository.get_submissions_by_team_and_question(
            contest_team.id, question_id
        )

        return [StudentSubmissionResponse.model_validate(sub) for sub in submissions]

    async def subscribe_submission_events(
        self, contest_id: UUID, user_id: UUID
    ) -> AsyncGenerator[ServerSentEvent, None]:
        """
        Subscribe to submission progress/status updates via Redis pubsub and yield them.
        """
        # Validate student eligibility, contest runtime status, session progress, and remaining time.
        (
            contest,
            contest_team,
            contest_team_member,
        ) = await self._validate_session_and_get_contest(
            contest_id=contest_id, user_id=user_id
        )

        pubsub = self.redis.pubsub()
        channel = get_contest_channel_key(
            contest_id, contest_team.team_id, contest_team_member.id
        )
        await pubsub.subscribe(channel)
        logger.info(f"Subscribed to {channel}")

        yield ServerSentEvent(comment="stream of contest lifecycle updates")

        try:
            while True:
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
