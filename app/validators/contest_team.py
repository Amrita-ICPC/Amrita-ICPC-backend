from app.exceptions.contest import TeamDisqualifiedError
from app.exceptions.contest import TeamCanceledError
from app.utils.enums import TeamStatus
from app.utils.enums import ContestTeamMemberStatus
from app.exceptions.student.teams import (
    InvalidContestTeamMemberStatusUpdateException,
    TeamMemberAccessDeniedError,
)
from uuid import UUID

class ContestTeamValidator:
    def __init__(self):
        pass

    @staticmethod
    def validate_members_are_in_team(team_member_ids: set[UUID], invitee_ids: list[UUID], team_name: str) -> None:
        """Validate that all invited members are part of the underlying team."""
        for user_id in invitee_ids:
            if user_id not in team_member_ids:
                raise TeamMemberAccessDeniedError(team_id=team_name, user_id=str(user_id))

    @staticmethod
    def validate_contest_team_member_life_cycle(current_status: ContestTeamMemberStatus, upcoming_status: ContestTeamMemberStatus) -> None:
        ALLOWED_LIFE_CYCLE_TRANSITIONS = {
            ContestTeamMemberStatus.INVITED: [ContestTeamMemberStatus.ACCEPTED, ContestTeamMemberStatus.REJECTED, ContestTeamMemberStatus.CANCELLED],
            ContestTeamMemberStatus.ACCEPTED: [ContestTeamMemberStatus.LEFT, ContestTeamMemberStatus.REMOVED],
            ContestTeamMemberStatus.LEFT: [ContestTeamMemberStatus.CANCELLED],
            ContestTeamMemberStatus.REJECTED: [ContestTeamMemberStatus.CANCELLED],
            ContestTeamMemberStatus.CANCELLED: [],
            ContestTeamMemberStatus.REMOVED: [ContestTeamMemberStatus.CANCELLED],
        }

        if upcoming_status not in ALLOWED_LIFE_CYCLE_TRANSITIONS[current_status]:
            raise InvalidContestTeamMemberStatusUpdateException()
    
    @staticmethod
    def validate_team_status(team_status: TeamStatus):
        """
        Raises if the team is canceled.
        """
        if team_status == TeamStatus.CANCELLED:
            raise TeamCanceledError()

        if team_status == TeamStatus.DISQUALIFIED:
            raise TeamDisqualifiedError()