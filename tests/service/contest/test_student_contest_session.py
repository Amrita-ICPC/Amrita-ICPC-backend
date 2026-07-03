"""Tests for StudentContestService.start_contest_session method."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.repositories.contest_runtime import ContestRuntimeRepository

from app.core.guards.contest_student import ContestStudentGuard
from app.exceptions.student.teams import (
    TeamLeaderAccessDeniedError,
)
from app.repositories.contest import ContestRepository
from app.repositories.contest_team_progress import ContestTeamProgressRepository
from app.repositories.student.contest import StudentContestRepository
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.team import TeamRepository
from app.schema.student.contest_team_progress import ContestTeamProgressResponse
from app.service.student.contests import StudentContestService
from app.utils.enums import (
    ContestRuntimeStatus,
    ContestStatus,
    ContestTeamParticpationType,
    TeamApprovalStatus,
    TeamStatus,
)


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def student_contest_service(mock_db):
    repository = AsyncMock(spec=StudentContestRepository)
    repository.db = mock_db
    contest_repository = AsyncMock(spec=ContestRepository)
    contest_team_repository = AsyncMock(spec=ContestTeamRepository)
    team_repository = MagicMock(spec=TeamRepository)
    contest_student_guard = AsyncMock(spec=ContestStudentGuard)
    contest_team_progress_repository = AsyncMock(spec=ContestTeamProgressRepository)
    contest_team_progress_repository.db = mock_db
    contest_runtime_repository = AsyncMock(spec=ContestRuntimeRepository)

    return StudentContestService(
        repository=repository,
        contest_repository=contest_repository,
        contest_team_reposiotry=contest_team_repository,
        team_repository=team_repository,
        contest_student_guard=contest_student_guard,
        contest_team_progress_repository=contest_team_progress_repository,
        contest_runtime_repository=contest_runtime_repository,
    )


@pytest.mark.asyncio
async def test_start_contest_session_success_new_session_shared(
    student_contest_service, mock_db
):
    contest_id = uuid4()
    contest_team_id = uuid4()
    user_id = uuid4()

    # Mock contest
    contest = MagicMock()
    contest.id = contest_id
    contest.status = ContestStatus.PUBLISHED
    contest.end_time = datetime.now(timezone.utc) + timedelta(hours=2)
    contest.duration = None
    contest.participation_type = (
        ContestTeamParticpationType.SHARED_SINGLE_EDITOR_WORKSPACE
    )
    student_contest_service.contest_repository.get_contest_or_raise.return_value = (
        contest
    )

    # Mock team
    contest_team = MagicMock()
    contest_team.id = contest_team_id
    contest_team.contest_id = contest_id
    contest_team.approval_status = TeamApprovalStatus.APPROVED
    contest_team.team_status = TeamStatus.CONFIRMED
    contest_team.leader_id = user_id

    # Mock team member
    member = MagicMock()
    member.user_id = user_id
    member.user.name = "Test Student"
    member.contest_team = contest_team

    student_contest_service.contest_team_repository.get_contest_team_member_by_user_id.return_value = member
    student_contest_service.contest_team_repository.get_contest_team_members.return_value = [
        member
    ]

    # Mock runtime
    runtime = MagicMock()
    runtime.runtime_status = ContestRuntimeStatus.RUNNING
    runtime.end_time = datetime.now(timezone.utc) + timedelta(hours=2)
    runtime.paused_at = None
    runtime.cancelled_at = None
    runtime.total_paused_duration = 0
    runtime.scoreboard_frozen = False
    student_contest_service.contest_runtime_repository.get_contest_runtime_by_id.return_value = runtime

    student_contest_service.contest_team_progress_repository.get_contest_team_progress_by_id.return_value = None
    student_contest_service.contest_team_progress_repository.get_contest_team_member_progress.return_value = None

    response = await student_contest_service.start_contest_session(contest_id, user_id)

    assert isinstance(response, ContestTeamProgressResponse)
    assert response.session.already_started is False
    assert response.permissions.can_edit is True
    assert response.permissions.can_submit is True
    student_contest_service.contest_team_progress_repository.create_contest_team_progress.assert_called_once()
    student_contest_service.contest_team_progress_repository.create_contest_team_member_progress.assert_called_once()

    # Assert created contest team progress properties
    team_progress_arg = student_contest_service.contest_team_progress_repository.create_contest_team_progress.call_args[
        0
    ][0]
    assert team_progress_arg.end_time is not None
    assert team_progress_arg.current_editor_user_id == user_id

    # Assert created member progress properties
    member_progress_arg = student_contest_service.contest_team_progress_repository.create_contest_team_member_progress.call_args[
        0
    ][0]
    assert member_progress_arg.end_time is None


@pytest.mark.asyncio
async def test_start_contest_session_success_reconnect_shared(
    student_contest_service, mock_db
):
    contest_id = uuid4()
    contest_team_id = uuid4()
    user_id = uuid4()

    # Mock contest
    contest = MagicMock()
    contest.id = contest_id
    contest.status = ContestStatus.PUBLISHED
    contest.end_time = datetime.now(timezone.utc) + timedelta(hours=2)
    contest.duration = None
    contest.participation_type = (
        ContestTeamParticpationType.SHARED_SINGLE_EDITOR_WORKSPACE
    )
    student_contest_service.contest_repository.get_contest_or_raise.return_value = (
        contest
    )

    # Mock team
    contest_team = MagicMock()
    contest_team.id = contest_team_id
    contest_team.contest_id = contest_id
    contest_team.approval_status = TeamApprovalStatus.APPROVED
    contest_team.team_status = TeamStatus.CONFIRMED
    contest_team.leader_id = user_id

    # Mock team member
    member = MagicMock()
    member.user_id = user_id
    member.user.name = "Test Student"
    member.contest_team = contest_team

    student_contest_service.contest_team_repository.get_contest_team_member_by_user_id.return_value = member
    student_contest_service.contest_team_repository.get_contest_team_members.return_value = [
        member
    ]

    # Mock progress record
    progress = MagicMock()
    progress.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    progress.end_time = datetime.now(timezone.utc) + timedelta(hours=1)
    progress.current_editor_user_id = user_id
    progress.score = 10
    progress.penalty = 20
    progress.solved_questions_count = 2
    progress.extra_time_seconds = 600

    # Mock runtime
    runtime = MagicMock()
    runtime.runtime_status = ContestRuntimeStatus.RUNNING
    runtime.end_time = datetime.now(timezone.utc) + timedelta(hours=2)
    runtime.paused_at = None
    runtime.cancelled_at = None
    runtime.total_paused_duration = 0
    runtime.scoreboard_frozen = False
    student_contest_service.contest_runtime_repository.get_contest_runtime_by_id.return_value = runtime

    student_contest_service.contest_team_progress_repository.get_contest_team_progress_by_id.return_value = progress

    response = await student_contest_service.start_contest_session(contest_id, user_id)

    assert isinstance(response, ContestTeamProgressResponse)
    assert response.session.already_started is True
    assert response.team_progress.score == 10
    assert response.team_progress.solved_count == 2
    assert response.team_progress.extra_time_seconds == 600
    assert response.team_progress.has_extra_time is True
    student_contest_service.contest_team_progress_repository.create_contest_team_progress.assert_not_called()


@pytest.mark.asyncio
async def test_start_contest_session_not_leader_new_session_raises(
    student_contest_service, mock_db
):
    contest_id = uuid4()
    contest_team_id = uuid4()
    user_id = uuid4()
    leader_id = uuid4()

    # Mock contest
    contest = MagicMock()
    contest.id = contest_id
    contest.status = ContestStatus.PUBLISHED
    contest.end_time = datetime.now(timezone.utc) + timedelta(hours=2)
    contest.duration = None
    contest.participation_type = (
        ContestTeamParticpationType.SHARED_SINGLE_EDITOR_WORKSPACE
    )
    student_contest_service.contest_repository.get_contest_or_raise.return_value = (
        contest
    )

    # Mock team
    contest_team = MagicMock()
    contest_team.id = contest_team_id
    contest_team.contest_id = contest_id
    contest_team.approval_status = TeamApprovalStatus.APPROVED
    contest_team.team_status = TeamStatus.CONFIRMED
    contest_team.leader_id = leader_id

    # Mock team member
    member = MagicMock()
    member.user_id = user_id
    member.user.name = "Test Student"
    member.contest_team = contest_team

    student_contest_service.contest_team_repository.get_contest_team_member_by_user_id.return_value = member
    student_contest_service.contest_student_guard.check_is_contest_team_leader.side_effect = TeamLeaderAccessDeniedError(
        str(contest_team_id), str(user_id)
    )

    # Mock runtime
    runtime = MagicMock()
    runtime.runtime_status = ContestRuntimeStatus.RUNNING
    runtime.end_time = datetime.now(timezone.utc) + timedelta(hours=2)
    runtime.paused_at = None
    runtime.cancelled_at = None
    runtime.total_paused_duration = 0
    runtime.scoreboard_frozen = False
    student_contest_service.contest_runtime_repository.get_contest_runtime_by_id.return_value = runtime

    student_contest_service.contest_team_progress_repository.get_contest_team_progress_by_id.return_value = None

    with pytest.raises(TeamLeaderAccessDeniedError):
        await student_contest_service.start_contest_session(contest_id, user_id)


@pytest.mark.asyncio
async def test_start_contest_session_success_individual_workspace(
    student_contest_service, mock_db
):
    contest_id = uuid4()
    contest_team_id = uuid4()
    user_id = uuid4()

    # Mock contest
    contest = MagicMock()
    contest.id = contest_id
    contest.status = ContestStatus.PUBLISHED
    contest.end_time = datetime.now(timezone.utc) + timedelta(hours=2)
    contest.duration = None
    contest.participation_type = ContestTeamParticpationType.INDIVIDUAL_WORKSPACE
    student_contest_service.contest_repository.get_contest_or_raise.return_value = (
        contest
    )

    # Mock team
    contest_team = MagicMock()
    contest_team.id = contest_team_id
    contest_team.contest_id = contest_id
    contest_team.approval_status = TeamApprovalStatus.APPROVED
    contest_team.team_status = TeamStatus.CONFIRMED
    contest_team.leader_id = user_id

    # Mock team member
    member = MagicMock()
    member.id = uuid4()
    member.user_id = user_id
    member.user.name = "Test Student"
    member.contest_team = contest_team

    student_contest_service.contest_team_repository.get_contest_team_member_by_user_id.return_value = member
    student_contest_service.contest_team_repository.get_contest_team_members.return_value = [
        member
    ]

    # Mock runtime
    runtime = MagicMock()
    runtime.runtime_status = ContestRuntimeStatus.RUNNING
    runtime.end_time = datetime.now(timezone.utc) + timedelta(hours=2)
    runtime.paused_at = None
    runtime.cancelled_at = None
    runtime.total_paused_duration = 0
    runtime.scoreboard_frozen = False
    student_contest_service.contest_runtime_repository.get_contest_runtime_by_id.return_value = runtime

    # Mock progress
    student_contest_service.contest_team_progress_repository.get_contest_team_progress_by_id.return_value = None
    student_contest_service.contest_team_progress_repository.get_contest_team_member_progress.return_value = None

    response = await student_contest_service.start_contest_session(contest_id, user_id)

    assert isinstance(response, ContestTeamProgressResponse)
    assert response.session.already_started is False
    # In individual workspace, permissions should allow editing
    assert response.permissions.can_edit is True
    assert response.permissions.can_submit is True
    student_contest_service.contest_team_progress_repository.create_contest_team_progress.assert_called_once()
    student_contest_service.contest_team_progress_repository.create_contest_team_member_progress.assert_called_once()

    # Assert created contest team progress properties
    team_progress_arg = student_contest_service.contest_team_progress_repository.create_contest_team_progress.call_args[
        0
    ][0]
    assert team_progress_arg.end_time is None
    assert team_progress_arg.current_editor_user_id is None

    # Assert created member progress properties
    member_progress_arg = student_contest_service.contest_team_progress_repository.create_contest_team_member_progress.call_args[
        0
    ][0]
    assert member_progress_arg.end_time is not None
