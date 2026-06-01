from uuid import UUID

from app.exceptions.contest import (
    ContestRuntimeFinishedError,
    QuestionNotInContestError,
)
from app.exceptions.student.contests import (
    ContestSessionNotStartedError,
    NoContestTeamMemberFoundError,
)
from app.models import Contest, ContestTeam, ContestTeamMember
from app.repositories.contest import ContestRepository
from app.repositories.contest_runtime import ContestRuntimeRepository
from app.repositories.contest_team_progress import ContestTeamProgressRepository
from app.repositories.student.contest_question import StudentContestQuestionRepository
from app.repositories.student.contest_team import ContestTeamRepository
from app.schema.student import (
    StudentContestQuestionResponse,
    StudentContestQuestionsListResponse,
    StudentQuestionDetailResponse,
    WorkspaceData,
)
from app.service.student.workspace import WorkspaceService
from app.utils.contest import calculate_effective_times
from app.utils.enums import (
    ContestRuntimeStatus,
    ContestTeamMemberStatus,
    ContestTeamParticpationType,
    TeamApprovalStatus,
    TeamStatus,
)
from app.utils.workspace_key_builder import build_workspace_key
from app.validators.contest_team import ContestTeamValidator


class StudentContestQuestionService:
    def __init__(
        self,
        repository: StudentContestQuestionRepository,
        contest_repository: ContestRepository,
        contest_team_repository: ContestTeamRepository,
        contest_runtime_repository: ContestRuntimeRepository,
        contest_team_progress_repository: ContestTeamProgressRepository,
        workspace_service: WorkspaceService,
    ):
        self.repository = repository
        self.contest_repository = contest_repository
        self.contest_team_repository = contest_team_repository
        self.contest_runtime_repository = contest_runtime_repository
        self.contest_team_progress_repository = contest_team_progress_repository
        self.workspace_service = workspace_service

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
                stauts=ContestTeamMemberStatus.ACCEPTED,
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

        # 4. Get and validate contest runtime status
        runtime = await self.contest_runtime_repository.get_contest_runtime_or_raise(
            contest_id
        )
        # Use validate_contest_runtime_for_session which raises on paused states
        ContestTeamValidator.validate_contest_runtime_for_session(runtime)

        # 5. Validate that progress exists (session is started)
        member_progress = await self.contest_team_progress_repository.get_contest_team_member_progress(
            contest_id=contest_id,
            contest_team_id=contest_team.id,
            contest_team_member_id=contest_team_member.id,
        )
        if member_progress is None:
            raise ContestSessionNotStartedError()

        team_progress = (
            await self.contest_team_progress_repository.get_contest_team_progress_by_id(
                contest_id=contest_id,
                contest_team_id=contest_team.id,
            )
        )
        if team_progress is None:
            raise ContestSessionNotStartedError()

        # 6. Validate session expiration (remaining seconds > 0)
        is_individual = (
            contest.participation_type
            == ContestTeamParticpationType.INDIVIDUAL_WORKSPACE
        )
        base_end_time = (
            member_progress.end_time if is_individual else team_progress.end_time
        )

        _, remaining_seconds = calculate_effective_times(
            base_end_time=base_end_time,
            total_paused_duration=runtime.total_paused_duration,
            extra_time_seconds=team_progress.extra_time_seconds,
            is_paused=(runtime.runtime_status == ContestRuntimeStatus.PAUSED),
            paused_at=runtime.paused_at,
        )

        if remaining_seconds <= 0:
            raise ContestRuntimeFinishedError()

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

        # Build key based on participation type
        is_individual = (
            contest.participation_type
            == ContestTeamParticpationType.INDIVIDUAL_WORKSPACE
        )
        if is_individual:
            return build_workspace_key(
                contest_id=contest_id,
                question_id=question_id,
                contest_team_member_id=contest_team_member.id,
            )
        else:
            return build_workspace_key(
                contest_id=contest_id,
                question_id=question_id,
                contest_team_id=contest_team.id,
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
