# app/validators/team.py
from app.exceptions.contest import TeamDisqualifiedError
from app.exceptions.contest import AccessDeniedTeamStatusError
from app.exceptions.contest import TeamCanceledError
from uuid import UUID

from app.exceptions.team import (
    CannotRemoveTeamLeaderError,
    InvalidLeaderAssignmentError,
    InvalidTeamSizeByModeError,
    InvalidTeamSizeError,
    MemberNotInTeamError,
    TeamAlreadyExistsError,
    TeamIsConfirmedError,
    LeaderMustBeMemberError,
    IndividualModeActionNotAllowedError,
)
from app.models.contest import Contest
from app.models.team import Team
from app.utils.enums import ContestMode, TeamStatus


class TeamValidator:
    """Validator for team business rules and constraints.

    This class implements the Validator Pattern, centralizing all business rule
    validation for team operations. It ensures data integrity and enforces
    domain-specific constraints before operations are executed.

    Responsibilities:
        - Validate team name uniqueness within contests
        - Enforce team size constraints (min/max, status-dependent)
        - Validate leader assignment rules
        - Check member existence in teams
        - Validate member eligibility

    Design Principles:
        - Single Responsibility: Only handles business rule validation
        - Stateless: All methods are static (no instance state)
        - Fail Fast: Raises domain exceptions immediately on violation
        - Reusable: Called by service layer before state changes

    Validation Methods:
        - validate_name_unique: Ensures team name is unique in contest
        - validate_team_size: Enforces min/max size constraints
        - validate_leader_assignment: Validates leader is a team member
        - validate_members_not_in_team: Prevents duplicate memberships
        - validate_members_in_team: Ensures members exist for removal
        - validate_leader_change: Validates leader reassignment rules

    Exception Strategy:
        - Raises domain-specific exceptions (InvalidTeamSizeError, etc.)
        - Provides clear error messages with context
        - Never modifies state (validation only)
    """

    @staticmethod
    def validate_name_unique(
        contest_id: UUID,
        name: str,
        existing_team: Team | None,
    ):
        """Raises if a team with the same name already exists in the contest."""
        if existing_team:
            raise TeamAlreadyExistsError(name, str(contest_id))

    @staticmethod
    def validate_team_size(
        num_members: int,
        contest: Contest,
        status: TeamStatus,
    ):
        """
        Raises if:
        - num_members exceeds contest max
        - status is CONFIRMED and num_members is below contest min
        """
        if num_members > contest.max_team_size:
            raise InvalidTeamSizeError(
                num_members, contest.min_team_size, contest.max_team_size
            )
        if status == TeamStatus.CONFIRMED and num_members < contest.min_team_size:
            raise InvalidTeamSizeError(
                num_members, contest.min_team_size, contest.max_team_size
            )

    @staticmethod
    def validate_leader_assignment(
        leader_id: UUID | None,
        member_ids: list[UUID],
        team_name: str,
    ) -> None:
        """
        Raises if:
        - leader_id is not in member_ids when member_ids is not empty
        """
        if leader_id is not None and member_ids and leader_id not in member_ids:
            raise InvalidLeaderAssignmentError(str(leader_id), team_name)

    @staticmethod
    def validate_members_not_in_team(
        existing_member_ids: set[UUID], new_member_ids: list[UUID], team_name: str
    ):
        """
        Validates that new members are not already in the team.

        Used when adding members to ensure no duplicate memberships.

        Args:
            existing_member_ids: Set of user IDs currently in the team
            new_member_ids: List of user IDs to be added
            team_name: Name of the team (for error message)

        Raises:
            MemberAlreadyInTeamError: If any new member is already in the team
        """
        from app.exceptions.team import MemberAlreadyInTeamError

        new_ids_set = set(new_member_ids)
        already_members = existing_member_ids.intersection(new_ids_set)

        if already_members:
            # Raise error for the first duplicate found
            duplicate_id = next(iter(already_members))
            raise MemberAlreadyInTeamError(str(duplicate_id), team_name)

    @staticmethod
    def validate_members_in_team(
        existing_member_ids: set[UUID], member_ids_to_check: set[UUID], team_name: str
    ):
        """
        Validates that specified members are currently in the team.

        Used when removing members to ensure they exist in the team.

        Args:
            existing_member_ids: Set of user IDs currently in the team
            member_ids_to_check: Set of user IDs to validate
            team_name: Name of the team (for error message)

        Raises:
            MemberNotInTeamError: If any member is not in the team
        """
        missing_members = member_ids_to_check - existing_member_ids
        if missing_members:
            # Raise error for the first missing member found
            missing_id = next(iter(missing_members))
            raise MemberNotInTeamError(str(missing_id), team_name)


    @staticmethod
    def validate_team_confirmation(team_status: TeamStatus, team_name: str)->None:
        """
        Raises if the team is confirmed.
        """
        if team_status == TeamStatus.CONFIRMED:
            raise TeamIsConfirmedError(team_name)

    @staticmethod
    def validate_allowed_student_team_status(team_status:TeamStatus)->None:
        allowed_team_statuses = {TeamStatus.CONFIRMED, TeamStatus.DRAFT, TeamStatus.CANCELLED}
        if team_status not in allowed_team_statuses:
            raise AccessDeniedTeamStatusError(team_status)

    @staticmethod
    def validate_leader_change(
        members_ids_to_remove: list[UUID],
        new_leader_id: UUID | None,
        current_leader_id: UUID | None,
        team_name: str,
    ) -> None:
        """
        Validates that the leader change is valid.

        Args:
            team: The team being updated
            new_leader_id: The new leader ID

        Raises:
            InvalidLeaderAssignmentError: If the new leader is not in the team
        """

        if current_leader_id in members_ids_to_remove and new_leader_id is None:
            raise CannotRemoveTeamLeaderError(team_name)
        if new_leader_id is not None and new_leader_id in members_ids_to_remove:
            raise InvalidLeaderAssignmentError(str(new_leader_id), team_name)

    @staticmethod
    def validate_team_size_by_contest_mode(
        members_count: int, contest_mode: ContestMode
    ):
        if contest_mode == ContestMode.INDIVIDUAL:
            if members_count != 1:
                raise InvalidTeamSizeByModeError()

    @staticmethod
    def validate_leader_in_members(
        leader_id: UUID,
        member_ids: list[UUID] | set[UUID],
        team_name: str,
    ) -> None:
        """
        Validates that the team leader is included in the list of member IDs.
        """
        if leader_id not in member_ids:
            raise LeaderMustBeMemberError(str(leader_id), team_name)

    @staticmethod
    def validate_team_operations_allowed(
        contest_mode: ContestMode,
        action: str,
    ) -> None:
        """
        Validates that the contest mode is not individual when performing team operations.
        """
        if contest_mode == ContestMode.INDIVIDUAL:
            raise IndividualModeActionNotAllowedError(action)

