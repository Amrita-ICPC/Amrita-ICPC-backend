"""Unit tests for TeamService.remove_team_member method.

This module provides comprehensive test coverage for removing members from teams:
- Permission validation
- Team size constraints after removal
- Member existence in team validation
- Leader succession handling
- Execution order guarantees

Tests follow the existing structure with organized test classes.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.team import (
    CannotRemoveTeamLeaderError,
    InvalidLeaderAssignmentError,
    InvalidTeamSizeError,
    MemberNotInTeamError,
    TeamNotFoundError,
)
from app.schema.team import TeamMemberRemove, TeamMembersResponse
from app.utils.enums import TeamStatus


class TestRemoveTeamMemberSuccess:
    """Test successful member removal scenarios."""

    @pytest.mark.asyncio
    async def test_returns_team_members_response(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that successful member removal returns TeamMembersResponse."""
        team_id = uuid4()
        member_to_remove = uuid4()
        remaining_member = uuid4()
        member_data = TeamMemberRemove(
            member_ids=[member_to_remove], new_leader_id=None
        )

        mock_team.leader_id = remaining_member
        mock_team.team_status = TeamStatus.DRAFT

        existing_members = [
            MagicMock(user_id=remaining_member),
            MagicMock(user_id=member_to_remove),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        mock_response = MagicMock(spec=TeamMembersResponse)

        with patch.object(team_service, "get_team_members", return_value=mock_response):
            result = await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        assert result == mock_response
        mock_repository.remove_team_members.assert_called_once()

    @pytest.mark.asyncio
    async def test_removes_single_member(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that a single member can be removed."""
        team_id = uuid4()
        member_to_remove = uuid4()
        member_data = TeamMemberRemove(
            member_ids=[member_to_remove], new_leader_id=None
        )

        mock_team.leader_id = None
        mock_team.team_status = TeamStatus.DRAFT

        existing_members = [
            MagicMock(user_id=uuid4()),
            MagicMock(user_id=member_to_remove),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        with patch.object(team_service, "get_team_members"):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.remove_team_members.assert_called_once_with(
            team_id=team_id, member_ids=[member_to_remove]
        )

    @pytest.mark.asyncio
    async def test_removes_multiple_members(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that multiple members can be removed at once."""
        team_id = uuid4()
        members_to_remove = [uuid4(), uuid4()]
        member_data = TeamMemberRemove(member_ids=members_to_remove, new_leader_id=None)

        mock_team.leader_id = None
        mock_team.team_status = TeamStatus.DRAFT

        existing_members = [
            MagicMock(user_id=uuid4()),
            MagicMock(user_id=members_to_remove[0]),
            MagicMock(user_id=members_to_remove[1]),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        with patch.object(team_service, "get_team_members"):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.remove_team_members.assert_called_once_with(
            team_id=team_id, member_ids=members_to_remove
        )

    @pytest.mark.asyncio
    async def test_removes_member_with_new_leader_assignment(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that leader can be reassigned when removing members."""
        team_id = uuid4()
        member_to_remove = uuid4()
        new_leader_id = uuid4()
        member_data = TeamMemberRemove(
            member_ids=[member_to_remove], new_leader_id=new_leader_id
        )

        mock_team.leader_id = member_to_remove
        mock_team.team_status = TeamStatus.DRAFT

        existing_members = [
            MagicMock(user_id=new_leader_id),
            MagicMock(user_id=member_to_remove),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        with patch.object(team_service, "get_team_members"):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        # Verify update_team is called with proper arguments
        assert mock_repository.update_team.call_count == 1
        call_args = mock_repository.update_team.call_args
        update_data, team, contest_team = call_args[0]
        assert update_data.team_id == team_id
        assert update_data.leader_id == new_leader_id

    @pytest.mark.asyncio
    async def test_removes_non_leader_member_without_leader_change(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that non-leader members can be removed without leader change."""
        team_id = uuid4()
        leader_id = uuid4()
        member_to_remove = uuid4()
        member_data = TeamMemberRemove(
            member_ids=[member_to_remove], new_leader_id=None
        )

        mock_team.leader_id = leader_id
        mock_team.team_status = TeamStatus.DRAFT

        existing_members = [
            MagicMock(user_id=leader_id),
            MagicMock(user_id=member_to_remove),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        with patch.object(team_service, "get_team_members"):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        # Verify update_team is called with proper arguments
        assert mock_repository.update_team.call_count == 1
        call_args = mock_repository.update_team.call_args
        update_data, team, contest_team = call_args[0]
        assert update_data.team_id == team_id
        assert update_data.leader_id is None


class TestRemoveTeamMemberContestValidation:
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
        member_data = TeamMemberRemove(member_ids=[uuid4()], new_leader_id=None)

        mock_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_guard.check_remove_team_members.assert_not_called()


class TestRemoveTeamMemberTeamValidation:
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
        member_data = TeamMemberRemove(member_ids=[uuid4()], new_leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.side_effect = TeamNotFoundError(
            str(team_id), str(contest_id)
        )

        with pytest.raises(TeamNotFoundError):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.remove_team_members.assert_not_called()


class TestRemoveTeamMemberPermissions:
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
        member_data = TeamMemberRemove(member_ids=[uuid4()], new_leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_guard.check_remove_team_members.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.get_team_or_raise.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_called_with_correct_args(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that guard is called with correct arguments."""
        team_id = uuid4()
        member_ids = [uuid4()]
        member_data = TeamMemberRemove(member_ids=member_ids, new_leader_id=None)

        mock_team.leader_id = None
        mock_team.team_status = TeamStatus.DRAFT

        existing_members = [
            MagicMock(user_id=uuid4()),
            MagicMock(user_id=member_ids[0]),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        with patch.object(team_service, "get_team_members"):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_guard.check_remove_team_members.assert_called_once_with(
            user_id=user_id, contest=mock_contest, member_ids=member_ids
        )


class TestRemoveTeamMemberMemberValidation:
    """Test member existence validation."""

    @pytest.mark.asyncio
    async def test_raises_when_member_not_in_team(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that MemberNotInTeamError is raised when member not in team."""
        team_id = uuid4()
        non_member_id = uuid4()
        member_data = TeamMemberRemove(member_ids=[non_member_id], new_leader_id=None)

        existing_members = [MagicMock(user_id=uuid4())]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        mock_validator.validate_members_in_team.side_effect = MemberNotInTeamError(
            str(non_member_id), "Team Alpha"
        )

        with pytest.raises(MemberNotInTeamError):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.remove_team_members.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_members_in_team_called_correctly(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that member validation is called with correct arguments."""
        team_id = uuid4()
        member_to_remove = uuid4()
        existing_member = uuid4()
        member_data = TeamMemberRemove(
            member_ids=[member_to_remove], new_leader_id=None
        )

        mock_team.name = "Team Alpha"
        mock_team.leader_id = None
        mock_team.team_status = TeamStatus.DRAFT

        existing_members = [
            MagicMock(user_id=existing_member),
            MagicMock(user_id=member_to_remove),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        with patch.object(team_service, "get_team_members"):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_validator.validate_members_in_team.assert_called_once_with(
            {existing_member, member_to_remove}, [member_to_remove], "Team Alpha"
        )


class TestRemoveTeamMemberSizeValidation:
    """Test team size constraint validation."""

    @pytest.mark.asyncio
    async def test_raises_when_removal_violates_min_size(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that InvalidTeamSizeError is raised when removal violates min size."""
        team_id = uuid4()
        member_to_remove = uuid4()
        member_data = TeamMemberRemove(
            member_ids=[member_to_remove], new_leader_id=None
        )

        mock_team.team_status = TeamStatus.CONFIRMED
        mock_contest.min_team_size = 2

        existing_members = [
            MagicMock(user_id=uuid4()),
            MagicMock(user_id=member_to_remove),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        mock_validator.validate_team_size.side_effect = InvalidTeamSizeError(
            1, mock_contest.min_team_size, mock_contest.max_team_size
        )

        with pytest.raises(InvalidTeamSizeError):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.remove_team_members.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_team_size_with_remaining_members(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that team size validation uses remaining member count."""
        team_id = uuid4()
        members_to_remove = [uuid4(), uuid4()]
        member_data = TeamMemberRemove(member_ids=members_to_remove, new_leader_id=None)

        mock_team.leader_id = None
        mock_team.team_status = TeamStatus.DRAFT

        existing_members = [
            MagicMock(user_id=uuid4()),
            MagicMock(user_id=uuid4()),
            MagicMock(user_id=members_to_remove[0]),
            MagicMock(user_id=members_to_remove[1]),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_contest_team = MagicMock()
        mock_contest_team.team_status = TeamStatus.DRAFT
        mock_contest_team.team = mock_team
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.get_all_team_members.return_value = existing_members

        with patch.object(team_service, "get_team_members"):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        # Should validate with 2 remaining members (4 total - 2 removed)
        mock_validator.validate_team_size.assert_called_once_with(
            2, mock_contest, mock_contest_team.team_status
        )


class TestRemoveTeamMemberLeaderValidation:
    """Test leader change validation."""

    @pytest.mark.asyncio
    async def test_raises_when_removing_leader_without_replacement(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that CannotRemoveTeamLeaderError is raised without replacement."""
        team_id = uuid4()
        current_leader_id = uuid4()
        member_data = TeamMemberRemove(
            member_ids=[current_leader_id], new_leader_id=None
        )

        mock_team.leader_id = current_leader_id
        mock_team.team_status = TeamStatus.CONFIRMED

        existing_members = [
            MagicMock(user_id=uuid4()),
            MagicMock(user_id=current_leader_id),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        mock_validator.validate_leader_change.side_effect = CannotRemoveTeamLeaderError(
            "Team Alpha"
        )

        with pytest.raises(CannotRemoveTeamLeaderError):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.remove_team_members.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_when_new_leader_is_being_removed(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that InvalidLeaderAssignmentError raised if new leader being removed."""
        team_id = uuid4()
        current_leader_id = uuid4()
        member_being_removed = uuid4()
        member_data = TeamMemberRemove(
            member_ids=[member_being_removed], new_leader_id=member_being_removed
        )

        mock_team.leader_id = current_leader_id
        mock_team.team_status = TeamStatus.DRAFT

        existing_members = [
            MagicMock(user_id=current_leader_id),
            MagicMock(user_id=member_being_removed),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        mock_validator.validate_leader_change.side_effect = (
            InvalidLeaderAssignmentError(str(member_being_removed), "Team Alpha")
        )

        with pytest.raises(InvalidLeaderAssignmentError):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.remove_team_members.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_leader_change_called_correctly(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that leader change validation is called with correct arguments."""
        team_id = uuid4()
        current_leader_id = uuid4()
        new_leader_id = uuid4()
        member_to_remove = uuid4()
        member_data = TeamMemberRemove(
            member_ids=[member_to_remove], new_leader_id=new_leader_id
        )

        mock_team.leader_id = current_leader_id
        mock_team.team_status = TeamStatus.DRAFT

        team_member_ids = {current_leader_id, new_leader_id, member_to_remove}
        existing_members = [MagicMock(user_id=uid) for uid in team_member_ids]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        with patch.object(team_service, "get_team_members"):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_validator.validate_leader_change.assert_called_once_with(
            [member_to_remove], new_leader_id, current_leader_id
        )


class TestRemoveTeamMemberExecutionOrder:
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
        member_data = TeamMemberRemove(member_ids=[uuid4()], new_leader_id=None)

        mock_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_guard.check_remove_team_members.assert_not_called()

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
        member_data = TeamMemberRemove(member_ids=[uuid4()], new_leader_id=None)

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_guard.check_remove_team_members.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.get_team_or_raise.assert_not_called()

    @pytest.mark.asyncio
    async def test_member_existence_validated_before_size(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that member existence is checked before size validation."""
        team_id = uuid4()
        non_member_id = uuid4()
        member_data = TeamMemberRemove(member_ids=[non_member_id], new_leader_id=None)

        existing_members = [MagicMock(user_id=uuid4())]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        mock_validator.validate_members_in_team.side_effect = MemberNotInTeamError(
            str(non_member_id), "Team Alpha"
        )

        with pytest.raises(MemberNotInTeamError):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_validator.validate_team_size.assert_not_called()

    @pytest.mark.asyncio
    async def test_size_validated_before_leader_change(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that size validation occurs before leader change validation."""
        team_id = uuid4()
        member_data = TeamMemberRemove(member_ids=[uuid4()], new_leader_id=None)

        mock_team.team_status = TeamStatus.CONFIRMED

        existing_members = [
            MagicMock(user_id=uuid4()),
            MagicMock(user_id=member_data.member_ids[0]),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        mock_validator.validate_team_size.side_effect = InvalidTeamSizeError(1, 2, 5)

        with pytest.raises(InvalidTeamSizeError):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_validator.validate_leader_change.assert_not_called()


class TestRemoveTeamMemberRepositoryContract:
    """Test the interface contract between service and repository."""

    @pytest.mark.asyncio
    async def test_remove_members_called_with_correct_args(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that remove_team_members is called with correct arguments."""
        team_id = uuid4()
        members_to_remove = [uuid4(), uuid4()]
        member_data = TeamMemberRemove(member_ids=members_to_remove, new_leader_id=None)

        mock_team.leader_id = None
        mock_team.team_status = TeamStatus.DRAFT

        existing_members = [
            MagicMock(user_id=uuid4()),
            MagicMock(user_id=members_to_remove[0]),
            MagicMock(user_id=members_to_remove[1]),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        with patch.object(team_service, "get_team_members"):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.remove_team_members.assert_called_once_with(
            team_id=team_id, member_ids=members_to_remove
        )

    @pytest.mark.asyncio
    async def test_update_team_called_with_new_leader(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that update_team is called with new leader when specified."""
        team_id = uuid4()
        new_leader_id = uuid4()
        member_data = TeamMemberRemove(
            member_ids=[uuid4()], new_leader_id=new_leader_id
        )

        mock_team.leader_id = uuid4()
        mock_team.team_status = TeamStatus.DRAFT

        existing_members = [
            MagicMock(user_id=new_leader_id),
            MagicMock(user_id=member_data.member_ids[0]),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        with patch.object(team_service, "get_team_members"):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        # Verify update_team is called with proper arguments
        assert mock_repository.update_team.call_count == 1
        call_args = mock_repository.update_team.call_args
        update_data, team, contest_team = call_args[0]
        assert update_data.team_id == team_id
        assert update_data.leader_id == new_leader_id

    @pytest.mark.asyncio
    async def test_update_team_called_with_none_when_no_leader(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that update_team is called with None when no leader specified."""
        team_id = uuid4()
        member_data = TeamMemberRemove(member_ids=[uuid4()], new_leader_id=None)

        mock_team.leader_id = None
        mock_team.team_status = TeamStatus.DRAFT

        existing_members = [
            MagicMock(user_id=uuid4()),
            MagicMock(user_id=member_data.member_ids[0]),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        with patch.object(team_service, "get_team_members"):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        # Verify update_team is called with proper arguments
        assert mock_repository.update_team.call_count == 1
        call_args = mock_repository.update_team.call_args
        update_data, team, contest_team = call_args[0]
        assert update_data.team_id == team_id
        assert update_data.leader_id is None

    @pytest.mark.asyncio
    async def test_get_team_members_called_after_removal(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that get_team_members is called to return updated member list."""
        team_id = uuid4()
        member_data = TeamMemberRemove(member_ids=[uuid4()], new_leader_id=None)

        mock_team.leader_id = None
        mock_team.team_status = TeamStatus.DRAFT

        existing_members = [
            MagicMock(user_id=uuid4()),
            MagicMock(user_id=member_data.member_ids[0]),
        ]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        with patch.object(team_service, "get_team_members") as mock_get_team_members:
            await team_service.remove_team_member(
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
        mock_team,
        contest_id,
        user_id,
    ):
        """Test that repository operations never called when validation fails."""
        team_id = uuid4()
        non_member_id = uuid4()
        member_data = TeamMemberRemove(member_ids=[non_member_id], new_leader_id=None)

        existing_members = [MagicMock(user_id=uuid4())]

        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_or_raise.return_value = mock_team
        mock_repository.get_all_team_members.return_value = existing_members

        mock_validator.validate_members_in_team.side_effect = MemberNotInTeamError(
            str(non_member_id), "Team Alpha"
        )

        with pytest.raises(MemberNotInTeamError):
            await team_service.remove_team_member(
                contest_id, team_id, member_data, user_id
            )

        mock_repository.remove_team_members.assert_not_called()
        mock_repository.update_team.assert_not_called()
