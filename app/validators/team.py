# app/validators/team_validator.py
from uuid import UUID

from app.exceptions.team import (
    InvalidLeaderAssignmentError,
    InvalidTeamSizeError,
    TeamAlreadyExistsError,
)
from app.models.contest import Contest
from app.models.team import Team
from app.utils.enums import TeamStatus


class TeamValidator:
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
        leader_id: UUID,
        member_ids: list[UUID],
    ):
        """
        Raises if:
        - leader_id is not in member_ids when member_ids is not empty
        """
        if member_ids and leader_id not in member_ids:
            raise InvalidLeaderAssignmentError("Leader must be one of the members.")
