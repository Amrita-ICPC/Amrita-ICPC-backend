"""Unit tests for TeamService.add_team_members method.

This module provides comprehensive test coverage for adding members to teams:
- Permission validation
- Team size constraints
- Member eligibility and existence
- Duplicate member prevention
- Leader assignment validation
- Execution order guarantees

Tests follow the existing structure with organized test classes.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.team import (
    InvalidTeamSizeError,
    MemberAlreadyInTeamError,
    TeamNotFoundError,
)
from app.exceptions.user import UserNotFoundError
from app.schema.team import TeamMemberAdd, TeamMemberResponse


class TestAddTeamMembersSuccess:
    """Test successful member addition scenarios."""

    @pytest.mark.asyncio
    async def test_returns_team_members_response(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that successful member addition returns TeamMembersResponse."""
        team_id = uuid4()
        new_member_ids = [uuid4(), uuid4()]
        member_data = TeamMemberAdd(member_ids=new_member_ids, leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_team_members_count_or_raise.return_value = 2
        mock_repository.get_all_team_members.return_value = []

        mock_response = (1, [MagicMock(spec=TeamMemberResponse)])

        with patch.object(team_service, "get_team_members", return_value=mock_response):
            result = await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        assert result == mock_response
        mock_repository.add_team_members.assert_called_once()

    @pytest.mark.asyncio
    async def test_adds_members_without_leader(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that members can be added without specifying a leader."""
        team_id = uuid4()
        new_member_ids = [uuid4()]
        member_data = TeamMemberAdd(member_ids=new_member_ids, leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_team_members_count_or_raise.return_value = 2
        mock_repository.get_all_team_members.return_value = []

        with patch.object(team_service, "get_team_members"):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        call_args = mock_repository.add_team_members.call_args[1]
        assert call_args["leader_id"] is None

    @pytest.mark.asyncio
    async def test_adds_members_with_new_leader_from_new_members(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that a new leader can be assigned from newly added members."""
        team_id = uuid4()
        leader_id = uuid4()
        new_member_ids = [leader_id, uuid4()]
        member_data = TeamMemberAdd(member_ids=new_member_ids, leader_id=leader_id)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_team_members_count_or_raise.return_value = 1
        mock_repository.get_all_team_members.return_value = []

        with patch.object(team_service, "get_team_members"):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        call_args = mock_repository.add_team_members.call_args[1]
        assert call_args["leader_id"] == leader_id


class TestAddTeamMembersContestValidation:
    """Test contest existence validation."""

    @pytest.mark.asyncio
    async def test_raises_when_contest_not_found(
        self,
        team_service,
        mock_repository,
        mock_guard,
        contest_id,
        user_id,
    ):
        """Test that ContestNotFoundError is raised when contest doesn't exist."""
        team_id = uuid4()
        member_data = TeamMemberAdd(member_ids=[uuid4()], leader_id=None)

        mock_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_guard.check_add_team_members.assert_not_called()


class TestAddTeamMembersTeamValidation:
    """Test team existence validation."""

    @pytest.mark.asyncio
    async def test_raises_when_team_not_found(
        self,
        team_service,
        mock_repository,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that TeamNotFoundError is raised when team doesn't exist."""
        team_id = uuid4()
        member_data = TeamMemberAdd(member_ids=[uuid4()], leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.side_effect = TeamNotFoundError(
            str(team_id), str(contest_id)
        )

        with pytest.raises(TeamNotFoundError):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.add_team_members.assert_not_called()


class TestAddTeamMembersPermissions:
    """Test permission validation."""

    @pytest.mark.asyncio
    async def test_raises_when_user_lacks_permission(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that PermissionDeniedError is raised when user lacks permission."""
        team_id = uuid4()
        member_data = TeamMemberAdd(member_ids=[uuid4()], leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_guard.check_add_team_members.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.get_contest_team_or_raise.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_called_with_correct_args(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that guard is called with correct arguments."""
        team_id = uuid4()
        member_ids = [uuid4(), uuid4()]
        member_data = TeamMemberAdd(member_ids=member_ids, leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_team_members_count_or_raise.return_value = 1
        mock_repository.get_all_team_members.return_value = []

        with patch.object(team_service, "get_team_members"):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_guard.check_add_team_members.assert_called_once_with(
            user_id=user_id, contest=mock_contest, member_ids=member_ids
        )


class TestAddTeamMembersSizeValidation:
    """Test team size constraint validation."""

    @pytest.mark.asyncio
    async def test_raises_when_would_exceed_max_size(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that InvalidTeamSizeError is raised when adding would exceed max."""
        team_id = uuid4()
        member_data = TeamMemberAdd(member_ids=[uuid4(), uuid4()], leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_team_members_count_or_raise.return_value = 4

        mock_validator.validate_team_size.side_effect = InvalidTeamSizeError(
            6, mock_contest.min_team_size, mock_contest.max_team_size
        )

        with pytest.raises(InvalidTeamSizeError):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.add_team_members.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_team_size_called_with_correct_count(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that team size validation is called with combined count."""
        team_id = uuid4()
        member_data = TeamMemberAdd(member_ids=[uuid4(), uuid4()], leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_team_members_count_or_raise.return_value = 2
        mock_repository.get_all_team_members.return_value = []

        with patch.object(team_service, "get_team_members"):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_validator.validate_team_size.assert_called_once_with(
            4, mock_contest, mock_contest_team.team_status
        )


class TestAddTeamMembersMemberValidation:
    """Test member existence and eligibility validation."""

    @pytest.mark.asyncio
    async def test_raises_when_member_not_found(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that UserNotFoundError is raised when member doesn't exist."""
        team_id = uuid4()
        invalid_member_id = uuid4()
        member_data = TeamMemberAdd(member_ids=[invalid_member_id], leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_team_members_count_or_raise.return_value = 2
        mock_repository.get_users_or_raise.side_effect = UserNotFoundError(
            str(invalid_member_id)
        )

        with pytest.raises(UserNotFoundError):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.add_team_members.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_when_member_already_in_team(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that MemberAlreadyInTeamError is raised for duplicate members."""
        team_id = uuid4()
        existing_member_id = uuid4()
        member_data = TeamMemberAdd(member_ids=[existing_member_id], leader_id=None)

        existing_member = MagicMock(user_id=existing_member_id)
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_team_members_count_or_raise.return_value = 2
        mock_repository.get_all_team_members.return_value = [existing_member]

        mock_validator.validate_members_not_in_team.side_effect = (
            MemberAlreadyInTeamError(str(existing_member_id), "Team Alpha")
        )

        with pytest.raises(MemberAlreadyInTeamError):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.add_team_members.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_members_not_in_team_called_correctly(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that duplicate member validation is called with correct args."""
        team_id = uuid4()
        new_member_ids = [uuid4(), uuid4()]
        existing_member_id = uuid4()
        member_data = TeamMemberAdd(member_ids=new_member_ids, leader_id=None)

        existing_member = MagicMock(user_id=existing_member_id)
        mock_contest_team.team.name = "Team Alpha"

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_team_members_count_or_raise.return_value = 1
        mock_repository.get_all_team_members.return_value = [existing_member]

        with patch.object(team_service, "get_team_members"):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_validator.validate_members_not_in_team.assert_called_once_with(
            {existing_member_id}, new_member_ids, "Team Alpha"
        )


class TestAddTeamMembersLeaderValidation:
    """Test leader assignment validation."""


class TestAddTeamMembersExecutionOrder:
    """Test the correct execution order of validation steps."""

    @pytest.mark.asyncio
    async def test_contest_validated_before_permissions(
        self,
        team_service,
        mock_repository,
        mock_guard,
        contest_id,
        user_id,
    ):
        """Test that contest validation occurs before permission checks."""
        team_id = uuid4()
        member_data = TeamMemberAdd(member_ids=[uuid4()], leader_id=None)

        mock_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_guard.check_add_team_members.assert_not_called()

    @pytest.mark.asyncio
    async def test_permissions_validated_before_team_fetch(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that permission check occurs before team fetch."""
        team_id = uuid4()
        member_data = TeamMemberAdd(member_ids=[uuid4()], leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_guard.check_add_team_members.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.get_contest_team_or_raise.assert_not_called()

    @pytest.mark.asyncio
    async def test_size_validated_before_member_existence(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that size validation occurs before checking member existence."""
        team_id = uuid4()
        member_data = TeamMemberAdd(member_ids=[uuid4()], leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_team_members_count_or_raise.return_value = 5

        mock_validator.validate_team_size.side_effect = InvalidTeamSizeError(6, 2, 5)

        with pytest.raises(InvalidTeamSizeError):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.get_users_or_raise.assert_not_called()

    @pytest.mark.asyncio
    async def test_member_existence_validated_before_duplicates(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that member existence is checked before duplicate validation."""
        team_id = uuid4()
        member_data = TeamMemberAdd(member_ids=[uuid4()], leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_team_members_count_or_raise.return_value = 2
        mock_repository.get_users_or_raise.side_effect = UserNotFoundError("user-id")

        with pytest.raises(UserNotFoundError):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_validator.validate_members_not_in_team.assert_not_called()


class TestAddTeamMembersRepositoryContract:
    """Test the interface contract between service and repository."""

    @pytest.mark.asyncio
    async def test_repository_called_with_correct_args(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that repository receives correct team_id, member_ids, and leader_id."""
        team_id = uuid4()
        member_ids = [uuid4(), uuid4()]
        leader_id = member_ids[0]
        member_data = TeamMemberAdd(member_ids=member_ids, leader_id=leader_id)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_team_members_count_or_raise.return_value = 1
        mock_repository.get_all_team_members.return_value = []

        with patch.object(team_service, "get_team_members"):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.add_team_members.assert_called_once_with(
            team_id=team_id, member_ids=member_ids, leader_id=leader_id
        )

    @pytest.mark.asyncio
    async def test_get_team_members_called_after_addition(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that get_team_members is called to return updated member list."""
        team_id = uuid4()
        member_data = TeamMemberAdd(member_ids=[uuid4()], leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_team_members_count_or_raise.return_value = 2
        mock_repository.get_all_team_members.return_value = []

        with patch.object(team_service, "get_team_members") as mock_get_team_members:
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

            mock_get_team_members.assert_called_once_with(contest_id, team_id, user_id)

    @pytest.mark.asyncio
    async def test_repository_never_called_when_validation_fails(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that repository operations never called when validation fails."""
        team_id = uuid4()
        member_data = TeamMemberAdd(member_ids=[uuid4()], leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_team_members_count_or_raise.return_value = 5

        mock_validator.validate_team_size.side_effect = InvalidTeamSizeError(6, 2, 5)

        with pytest.raises(InvalidTeamSizeError):
            await team_service.add_team_members(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.add_team_members.assert_not_called()
