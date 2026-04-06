"""Comprehensive tests for TeamService.create_team method.

This module contains thorough test coverage for the team creation functionality,
organized into logical test classes that cover different aspects of the operation:

- Success scenarios: Valid team creation with various configurations
- Contest validation: Testing contest existence and retrieval
- Permission validation: Testing user authorization and access control
- Name validation: Testing team name uniqueness within contests
- Size validation: Testing team size constraints and rules
- Member validation: Testing member existence and eligibility
- Leader validation: Testing leader assignment rules
- Execution order: Testing the correct sequence of validation steps
- Repository contract: Testing the interface between service and repository

Each test class focuses on a specific validation concern, making the test suite
easy to navigate and maintain. The tests use mocked dependencies to isolate
the service layer logic and ensure fast, reliable test execution.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.team import (
    InvalidLeaderAssignmentError,
    InvalidTeamSizeError,
    TeamAlreadyExistsError,
)
from app.exceptions.user import UserNotFoundError
from app.schema.team import ContestTeamResponse, TeamCreate
from app.utils.enums import TeamStatus


class TestCreateTeamSuccess:
    """Test successful team creation scenarios."""

    @pytest.mark.asyncio
    async def test_returns_contest_team_response(
        self,
        team_service,
        mock_repository,
        mock_contest_team,
        mock_contest_team_response,
        contest_id,
        team_data,
        user_id,
    ):
        """Test that successful team creation returns ContestTeamResponse."""
        mock_repository.find_team_by_name.return_value = None
        mock_repository.create_team.return_value = mock_contest_team

        with patch.object(
            ContestTeamResponse,
            "from_contest_team",
            return_value=mock_contest_team_response,
        ):
            result = await team_service.create_team(contest_id, team_data, user_id)

        assert result == mock_contest_team_response

    @pytest.mark.asyncio
    async def test_draft_team_below_min_size_succeeds(
        self,
        team_service,
        mock_repository,
        setup_valid_contest,
        contest_id,
        user_id,
    ):
        """Test that DRAFT teams can have fewer members than minimum size."""
        draft_team = TeamCreate(
            name="Draft Team",
            description=None,
            logo=None,
            member_ids=[uuid4()],
            leader_id=None,
            status=TeamStatus.DRAFT,
        )
        mock_repository.find_team_by_name.return_value = None
        mock_repository.create_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.create_team(contest_id, draft_team, user_id)

    @pytest.mark.asyncio
    async def test_team_without_leader_succeeds(
        self,
        team_service,
        mock_repository,
        setup_valid_contest,
        contest_id,
        member_ids,
        user_id,
    ):
        """Test that teams can be created without specifying a leader."""
        no_leader_team = TeamCreate(
            name="No Leader Team",
            description=None,
            logo=None,
            member_ids=member_ids,
            leader_id=None,
            status=TeamStatus.DRAFT,
        )
        mock_repository.find_team_by_name.return_value = None
        mock_repository.create_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.create_team(contest_id, no_leader_team, user_id)


class TestCreateTeamContestValidation:
    """Test contest existence and retrieval validation."""

    @pytest.mark.asyncio
    async def test_raises_when_contest_not_found(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_validator,
        contest_id,
        team_data,
        user_id,
    ):
        """Test that ContestNotFoundError is raised when contest doesn't exist."""
        mock_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await team_service.create_team(contest_id, team_data, user_id)

        mock_guard.check_create_team.assert_not_called()
        mock_validator.validate_name_unique.assert_not_called()


class TestCreateTeamPermissions:
    """Test permission and authorization validation."""

    @pytest.mark.asyncio
    async def test_raises_when_user_lacks_permission(
        self,
        team_service,
        mock_guard,
        mock_validator,
        setup_valid_contest,
        contest_id,
        team_data,
        user_id,
    ):
        """Test that PermissionDeniedError is raised when user lacks permission."""
        mock_guard.check_create_team.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await team_service.create_team(contest_id, team_data, user_id)

        mock_validator.validate_name_unique.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_called_with_correct_args(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_contest,
        setup_valid_contest,
        contest_id,
        team_data,
        user_id,
    ):
        """Test that guard is called with correct arguments."""
        mock_repository.find_team_by_name.return_value = None
        mock_repository.create_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.create_team(contest_id, team_data, user_id)

        mock_guard.check_create_team.assert_called_once_with(
            user_id=user_id,
            contest=mock_contest,
            member_ids=team_data.member_ids,
        )


class TestCreateTeamNameValidation:
    """Test team name uniqueness validation within contests."""

    @pytest.mark.asyncio
    async def test_raises_when_name_already_exists(
        self,
        team_service,
        mock_repository,
        mock_validator,
        setup_valid_contest,
        contest_id,
        team_data,
        user_id,
    ):
        """Test that TeamAlreadyExistsError is raised for duplicate team names."""
        mock_repository.find_team_by_name.return_value = MagicMock()
        mock_validator.validate_name_unique.side_effect = TeamAlreadyExistsError(
            team_data.name, str(contest_id)
        )

        with pytest.raises(TeamAlreadyExistsError):
            await team_service.create_team(contest_id, team_data, user_id)

        mock_repository.create_team.assert_not_called()

    @pytest.mark.asyncio
    async def test_find_team_by_name_called_with_correct_args(
        self,
        team_service,
        mock_repository,
        setup_valid_contest,
        contest_id,
        team_data,
        user_id,
    ):
        """Test that team name lookup is called with correct parameters."""
        mock_repository.find_team_by_name.return_value = None
        mock_repository.create_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.create_team(contest_id, team_data, user_id)

        mock_repository.find_team_by_name.assert_called_once_with(
            contest_id, team_data.name
        )


class TestCreateTeamSizeValidation:
    """Test team size constraint validation."""

    @pytest.mark.asyncio
    async def test_raises_when_exceeds_max_size(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        setup_valid_contest,
        contest_id,
        user_id,
    ):
        """Test that InvalidTeamSizeError is raised when team exceeds maximum size."""
        oversized_team = TeamCreate(
            name="Big Team",
            description=None,
            logo=None,
            member_ids=[uuid4() for _ in range(6)],
            leader_id=None,
            status=TeamStatus.DRAFT,
        )
        mock_repository.find_team_by_name.return_value = None
        mock_validator.validate_team_size.side_effect = InvalidTeamSizeError(
            6, mock_contest.min_team_size, mock_contest.max_team_size
        )

        with pytest.raises(InvalidTeamSizeError):
            await team_service.create_team(contest_id, oversized_team, user_id)

    @pytest.mark.asyncio
    async def test_raises_when_confirmed_below_min_size(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        setup_valid_contest,
        contest_id,
        user_id,
    ):
        """Test that confirmed teams must meet minimum size requirement."""
        small_confirmed = TeamCreate(
            name="Small Team",
            description=None,
            logo=None,
            member_ids=[uuid4()],
            leader_id=None,
            status=TeamStatus.CONFIRMED,
        )
        mock_repository.find_team_by_name.return_value = None
        mock_validator.validate_team_size.side_effect = InvalidTeamSizeError(
            1, mock_contest.min_team_size, mock_contest.max_team_size
        )

        with pytest.raises(InvalidTeamSizeError):
            await team_service.create_team(contest_id, small_confirmed, user_id)

    @pytest.mark.asyncio
    async def test_validate_team_size_called_with_correct_args(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        setup_valid_contest,
        contest_id,
        team_data,
        user_id,
    ):
        """Test that team size validation is called with correct parameters."""
        mock_repository.find_team_by_name.return_value = None
        mock_repository.create_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.create_team(contest_id, team_data, user_id)

        mock_validator.validate_team_size.assert_called_once_with(
            len(team_data.member_ids),
            mock_contest,
            team_data.status,
        )


class TestCreateTeamMemberValidation:
    """Test team member existence and eligibility validation."""

    @pytest.mark.asyncio
    async def test_raises_when_member_not_found(
        self,
        team_service,
        mock_repository,
        setup_valid_contest,
        contest_id,
        team_data,
        user_id,
    ):
        """Test that UserNotFoundError is raised when a member doesn't exist."""
        mock_repository.find_team_by_name.return_value = None
        mock_repository.get_users_or_raise.side_effect = UserNotFoundError(
            str(team_data.member_ids[0])
        )

        with pytest.raises(UserNotFoundError):
            await team_service.create_team(contest_id, team_data, user_id)

        mock_repository.create_team.assert_not_called()


class TestCreateTeamLeaderValidation:
    """Test team leader assignment validation."""

    @pytest.mark.asyncio
    async def test_raises_when_leader_not_in_member_ids(
        self,
        team_service,
        mock_repository,
        mock_validator,
        setup_valid_contest,
        contest_id,
        member_ids,
        user_id,
    ):
        """Test that leader must be one of the team members."""
        bad_leader_team = TeamCreate(
            name="Team Alpha",
            description=None,
            logo=None,
            member_ids=member_ids,
            leader_id=uuid4(),
            status=TeamStatus.DRAFT,
        )
        mock_repository.find_team_by_name.return_value = None
        mock_validator.validate_leader_assignment.side_effect = (
            InvalidLeaderAssignmentError(str(uuid4()), "Team Alpha")
        )

        with pytest.raises(InvalidLeaderAssignmentError):
            await team_service.create_team(contest_id, bad_leader_team, user_id)

        mock_repository.create_team.assert_not_called()


class TestCreateTeamExecutionOrder:
    """Test the correct execution order of validation steps."""

    @pytest.mark.asyncio
    async def test_contest_fetched_before_guard(
        self,
        team_service,
        mock_repository,
        mock_guard,
        contest_id,
        team_data,
        user_id,
    ):
        """Test that contest validation occurs before permission checks."""
        mock_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await team_service.create_team(contest_id, team_data, user_id)

        mock_guard.check_create_team.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_called_before_name_validation(
        self,
        team_service,
        mock_guard,
        mock_validator,
        setup_valid_contest,
        contest_id,
        team_data,
        user_id,
    ):
        """Test that permission validation occurs before name validation."""
        mock_guard.check_create_team.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await team_service.create_team(contest_id, team_data, user_id)

        mock_validator.validate_name_unique.assert_not_called()

    @pytest.mark.asyncio
    async def test_members_validated_before_leader(
        self,
        team_service,
        mock_repository,
        mock_validator,
        setup_valid_contest,
        contest_id,
        team_data,
        user_id,
    ):
        """Test that member validation occurs before leader validation."""
        mock_repository.find_team_by_name.return_value = None
        mock_repository.get_users_or_raise.side_effect = UserNotFoundError("some-id")

        with pytest.raises(UserNotFoundError):
            await team_service.create_team(contest_id, team_data, user_id)

        mock_validator.validate_leader_assignment.assert_not_called()


class TestCreateTeamRepositoryContract:
    """Test the interface contract between service and repository layers."""

    @pytest.mark.asyncio
    async def test_repository_called_with_correct_domain_object(
        self,
        team_service,
        mock_repository,
        setup_valid_contest,
        contest_id,
        team_data,
        user_id,
    ):
        """Test that repository receives correctly mapped ORM entities.

        This validates the service-repository contract and ensures that
        SQLAlchemy changes won't break the service layer interface.
        """
        mock_repository.find_team_by_name.return_value = None
        mock_repository.create_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.create_team(contest_id, team_data, user_id)

        mock_repository.create_team.assert_called_once()
        call_kwargs = mock_repository.create_team.call_args.kwargs
        assert call_kwargs["team"].name == team_data.name
        assert call_kwargs["contest_team"].contest_id == contest_id
        assert call_kwargs["contest_team"].team_status == team_data.status
        assert len(call_kwargs["team_users"]) == len(team_data.member_ids)

    @pytest.mark.asyncio
    async def test_repository_never_called_when_validation_fails(
        self,
        team_service,
        mock_repository,
        mock_validator,
        setup_valid_contest,
        contest_id,
        team_data,
        user_id,
    ):
        """Test that repository operations are never called when validation fails.

        This ensures no partial writes occur when team creation fails.
        """
        mock_repository.find_team_by_name.return_value = MagicMock()
        mock_validator.validate_name_unique.side_effect = TeamAlreadyExistsError(
            team_data.name, str(contest_id)
        )

        with pytest.raises(TeamAlreadyExistsError):
            await team_service.create_team(contest_id, team_data, user_id)

        mock_repository.create_team.assert_not_called()
