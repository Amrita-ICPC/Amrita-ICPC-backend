from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.exceptions.contest import QuestionNotInContestError
from app.exceptions.student.contests import (
    ContestSessionEndedError,
    ContestSessionNotStartedError,
)
from app.models import Contest, ContestTeam, ContestTeamMember, ContestTeamProgress
from app.repositories.contest import ContestRepository
from app.repositories.contest_team_progress import ContestTeamProgressRepository
from app.repositories.judge0 import Judge0Repository
from app.repositories.question import QuestionRepository
from app.repositories.student.contest_question import StudentContestQuestionRepository
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.testcase import TestCaseRepository
from app.schema.student.submission import StudentSubmissionResponse
from app.service.student.contest_question import StudentContestQuestionService
from app.service.student.workspace import WorkspaceService
from app.utils.enums import (
    ContestTeamParticipationType,
    TeamApprovalStatus,
    TeamStatus,
)


@pytest.fixture
def mock_repository():
    return AsyncMock(spec=StudentContestQuestionRepository)


@pytest.fixture
def mock_contest_repository():
    return AsyncMock(spec=ContestRepository)


@pytest.fixture
def mock_contest_team_repository():
    return AsyncMock(spec=ContestTeamRepository)


@pytest.fixture
def mock_contest_team_progress_repository():
    return AsyncMock(spec=ContestTeamProgressRepository)


@pytest.fixture
def mock_testcase_repository():
    return AsyncMock(spec=TestCaseRepository)


@pytest.fixture
def mock_workspace_service():
    return AsyncMock(spec=WorkspaceService)


@pytest.fixture
def mock_judge0_repository():
    return AsyncMock(spec=Judge0Repository)


@pytest.fixture
def mock_question_repository():
    return AsyncMock(spec=QuestionRepository)


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def contest_question_service(
    mock_repository,
    mock_contest_repository,
    mock_contest_team_repository,
    mock_contest_team_progress_repository,
    mock_testcase_repository,
    mock_workspace_service,
    mock_judge0_repository,
    mock_question_repository,
    mock_redis,
):
    return StudentContestQuestionService(
        repository=mock_repository,
        contest_repository=mock_contest_repository,
        contest_team_repository=mock_contest_team_repository,
        contest_team_progress_repository=mock_contest_team_progress_repository,
        testcase_repository=mock_testcase_repository,
        workspace_service=mock_workspace_service,
        judge0_repository=mock_judge0_repository,
        question_repository=mock_question_repository,
        redis=mock_redis,
    )


@pytest.mark.asyncio
async def test_submit_code_success(
    contest_question_service,
    mock_contest_repository,
    mock_contest_team_repository,
    mock_contest_team_progress_repository,
    mock_testcase_repository,
    mock_question_repository,
):
    # Setup test variables
    contest_id = uuid4()
    question_id = uuid4()
    user_id = uuid4()
    code = "print('hello')"
    language_id = 54

    # Mock contest
    contest = MagicMock(spec=Contest)
    contest.id = contest_id
    contest.participation_type = ContestTeamParticipationType.INDIVIDUAL_WORKSPACE
    mock_contest_repository.get_contest_or_raise.return_value = contest

    # Mock team member
    team_member = MagicMock(spec=ContestTeamMember)
    team_member.id = uuid4()
    contest_team = MagicMock(spec=ContestTeam)
    contest_team.id = uuid4()
    contest_team.contest_id = contest_id
    contest_team.team_status = TeamStatus.CONFIRMED
    contest_team.approval_status = TeamApprovalStatus.APPROVED
    team_member.contest_team = contest_team
    mock_contest_team_repository.get_contest_team_member_by_user_id.return_value = (
        team_member
    )

    # Mock session progress
    progress = MagicMock(spec=ContestTeamProgress)
    progress.end_time = datetime.now(timezone.utc).replace(year=2030)  # far in future
    progress.extra_time_seconds = 0
    mock_contest_team_progress_repository.get_contest_team_progress_by_id.return_value = progress

    # Mock question existence in contest
    mock_contest_repository.is_question_in_contest.return_value = True

    # Mock testcases count
    mock_testcase_repository.get_all_by_question.return_value = [
        MagicMock(),
        MagicMock(),
    ]

    # Mock create_submission to return a submission ORM-like structure
    mock_submission = None

    async def mock_create_submission(submission, contest_submission=None):
        nonlocal mock_submission
        submission.id = uuid4()
        submission.created_at = datetime.now(timezone.utc)
        mock_submission = submission
        return submission

    mock_question_repository.create_submission.side_effect = mock_create_submission

    from unittest.mock import patch

    # Call submit_code and mock celery_app.send_task & ContestEventService
    with (
        patch(
            "app.service.student.contest_question.celery_app.send_task"
        ) as mock_send_task,
        patch(
            "app.service.student.contest_question.ContestEventService"
        ) as mock_event_service_class,
    ):
        mock_event_service = AsyncMock()
        mock_event_service_class.return_value = mock_event_service

        response = await contest_question_service.submit_code(
            contest_id=contest_id,
            question_id=question_id,
            user_id=user_id,
            code=code,
            language_id=language_id,
        )

        # Asserts
        assert isinstance(response, StudentSubmissionResponse)
        assert response.question_id == question_id
        assert response.language_id == language_id
        assert response.status is None
        assert response.total_testcases == 2
        assert mock_submission is not None
        assert mock_submission.source_code == code
        mock_question_repository.create_submission.assert_called_once()
        mock_send_task.assert_called_once_with(
            "worker.evaluation.evaluate_submission",
            args=[str(mock_submission.id)],
        )
        mock_event_service.publish_event.assert_called_once()


@pytest.mark.asyncio
async def test_submit_code_question_not_in_contest(
    contest_question_service,
    mock_contest_repository,
    mock_contest_team_repository,
    mock_contest_team_progress_repository,
):
    contest_id = uuid4()
    question_id = uuid4()
    user_id = uuid4()

    # Mock contest, member and progress to bypass session validation
    contest = MagicMock(spec=Contest)
    contest.id = contest_id
    contest.participation_type = ContestTeamParticipationType.INDIVIDUAL_WORKSPACE
    mock_contest_repository.get_contest_or_raise.return_value = contest

    team_member = MagicMock(spec=ContestTeamMember)
    team_member.id = uuid4()
    contest_team = MagicMock(spec=ContestTeam)
    contest_team.id = uuid4()
    contest_team.contest_id = contest_id
    contest_team.team_status = TeamStatus.CONFIRMED
    contest_team.approval_status = TeamApprovalStatus.APPROVED
    team_member.contest_team = contest_team
    mock_contest_team_repository.get_contest_team_member_by_user_id.return_value = (
        team_member
    )

    progress = MagicMock(spec=ContestTeamProgress)
    progress.end_time = datetime.now(timezone.utc).replace(year=2030)
    progress.extra_time_seconds = 0
    mock_contest_team_progress_repository.get_contest_team_progress_by_id.return_value = progress

    # Question is NOT in contest
    mock_contest_repository.is_question_in_contest.return_value = False

    with pytest.raises(QuestionNotInContestError):
        await contest_question_service.submit_code(
            contest_id=contest_id,
            question_id=question_id,
            user_id=user_id,
            code="print(1)",
            language_id=54,
        )


@pytest.mark.asyncio
async def test_submit_code_session_not_started(
    contest_question_service,
    mock_contest_repository,
    mock_contest_team_repository,
    mock_contest_team_progress_repository,
):
    contest_id = uuid4()
    question_id = uuid4()
    user_id = uuid4()

    # Mock contest and team member
    contest = MagicMock(spec=Contest)
    contest.id = contest_id
    contest.participation_type = ContestTeamParticipationType.INDIVIDUAL_WORKSPACE
    mock_contest_repository.get_contest_or_raise.return_value = contest

    team_member = MagicMock(spec=ContestTeamMember)
    team_member.id = uuid4()
    contest_team = MagicMock(spec=ContestTeam)
    contest_team.id = uuid4()
    contest_team.contest_id = contest_id
    contest_team.team_status = TeamStatus.CONFIRMED
    contest_team.approval_status = TeamApprovalStatus.APPROVED
    team_member.contest_team = contest_team
    mock_contest_team_repository.get_contest_team_member_by_user_id.return_value = (
        team_member
    )

    # Mock session not started (progress is None)
    mock_contest_team_progress_repository.get_contest_team_progress_by_id.return_value = None

    with pytest.raises(ContestSessionNotStartedError):
        await contest_question_service.submit_code(
            contest_id=contest_id,
            question_id=question_id,
            user_id=user_id,
            code="print(1)",
            language_id=54,
        )


@pytest.mark.asyncio
async def test_submit_code_session_ended(
    contest_question_service,
    mock_contest_repository,
    mock_contest_team_repository,
    mock_contest_team_progress_repository,
):
    contest_id = uuid4()
    question_id = uuid4()
    user_id = uuid4()

    # Mock contest and team member
    contest = MagicMock(spec=Contest)
    contest.id = contest_id
    contest.participation_type = ContestTeamParticipationType.INDIVIDUAL_WORKSPACE
    mock_contest_repository.get_contest_or_raise.return_value = contest

    team_member = MagicMock(spec=ContestTeamMember)
    team_member.id = uuid4()
    contest_team = MagicMock(spec=ContestTeam)
    contest_team.id = uuid4()
    contest_team.contest_id = contest_id
    contest_team.team_status = TeamStatus.CONFIRMED
    contest_team.approval_status = TeamApprovalStatus.APPROVED
    team_member.contest_team = contest_team
    mock_contest_team_repository.get_contest_team_member_by_user_id.return_value = (
        team_member
    )

    # Mock session ended (end_time in past)
    progress = MagicMock(spec=ContestTeamProgress)
    progress.end_time = datetime.now(timezone.utc).replace(year=2020)
    progress.extra_time_seconds = 0
    mock_contest_team_progress_repository.get_contest_team_progress_by_id.return_value = progress

    with pytest.raises(ContestSessionEndedError):
        await contest_question_service.submit_code(
            contest_id=contest_id,
            question_id=question_id,
            user_id=user_id,
            code="print(1)",
            language_id=54,
        )
