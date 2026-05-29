from uuid import UUID

from fastapi import status

from app.exceptions.base import AppBaseException
from app.exceptions.contest import (
    ContestMaxTeamsReachedError,
    ContestTeamNotFoundException,
    TeamCanceledError,
    TeamDisqualifiedError,
    ContestRuntimeNotInitializedError,
    ContestRuntimeCancelledError,
    ContestRuntimeFinishedError,
    ContestRuntimePausedError,
)
from app.exceptions.student.teams import (
    InvalidContestTeamMemberStatusUpdateException,
    TeamMemberAccessDeniedError,
)
from app.models import ContestTeam, ContestRuntime
from app.utils.enums import ContestTeamMemberStatus, TeamApprovalStatus, TeamStatus, ContestRuntimeStatus


class ContestTeamValidator:
    def __init__(self)->None:
        pass

    @staticmethod
    def validate_contest_runtime_for_session(contest_runtime: ContestRuntime | None) -> None:
        """
        Validate the contest runtime status and expiration for starting a session.

        Args:
            contest_runtime: The ContestRuntime model instance or None.

        Raises:
            ContestRuntimeNotInitializedError: If the runtime is None.
            ContestRuntimeCancelledError: If the runtime is cancelled.
            ContestRuntimeFinishedError: If the runtime is finished or ended.
            ContestRuntimePausedError: If the runtime is paused.
        """
        if contest_runtime is None:
            raise ContestRuntimeNotInitializedError()

        if contest_runtime.runtime_status == ContestRuntimeStatus.CANCELLED or contest_runtime.cancelled_at is not None:
            raise ContestRuntimeCancelledError()

        if contest_runtime.runtime_status == ContestRuntimeStatus.FINISHED:
            raise ContestRuntimeFinishedError()

        if contest_runtime.runtime_status == ContestRuntimeStatus.PAUSED:
            raise ContestRuntimePausedError()

        from datetime import datetime, timezone
        current_time = datetime.now(timezone.utc)
        if contest_runtime.end_time is not None and current_time > contest_runtime.end_time:
            raise ContestRuntimeFinishedError()

    @staticmethod
    def validate_members_are_in_team(team_member_ids: set[UUID], invitee_ids: list[UUID], team_name: str) -> None:
        """Validate that all invited members are part of the underlying team."""
        for user_id in invitee_ids:
            if user_id not in team_member_ids:
                raise TeamMemberAccessDeniedError(team_id=team_name, user_id=str(user_id))

    @staticmethod
    def validate_team_membership_if_needed(
        team_id: UUID | None,
        team_member_ids: set[UUID],
        invitee_ids: list[UUID],
        team_name: str,
    ) -> None:
        """Validate that all invited members are part of the underlying team if the team exists."""
        if team_id is not None:
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
    def validate_team_status(team_status: TeamStatus)->None:
        """
        Raises if the team is canceled.
        """
        if team_status == TeamStatus.CANCELLED:
            raise TeamCanceledError()

        if team_status == TeamStatus.DISQUALIFIED:
            raise TeamDisqualifiedError()

    @staticmethod
    def validate_max_teams(
        approved_teams_count: int, max_teams: int | None, contest_id: UUID
    ) -> None:
        """Validate that the number of approved teams does not exceed the contest limit."""
        if max_teams is not None and max_teams > 0:
            if approved_teams_count >= max_teams:
                raise ContestMaxTeamsReachedError(str(contest_id), max_teams)

    @staticmethod
    def validate_contest_team_for_session(contest_team: ContestTeam, contest_id: UUID) -> None:
        """
        Validate a contest team status and approval for starting a session.

        Args:
            contest_team: ContestTeam model instance.
            contest_id: UUID of the contest.

        Raises:
            ContestTeamNotFoundException: If the team does not belong to the contest.
            AppBaseException: If the team is not approved or is in draft status.
            TeamDisqualifiedError: If the team is disqualified.
            TeamCanceledError: If the team is cancelled.
        """
        if contest_team.contest_id != contest_id:
            raise ContestTeamNotFoundException(str(contest_team.id))

        if contest_team.approval_status != TeamApprovalStatus.APPROVED:
            raise AppBaseException(
                message="Team is not approved by contest organizers",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if contest_team.team_status == TeamStatus.DRAFT:
            raise AppBaseException(
                message="Team is in draft status",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        elif contest_team.team_status == TeamStatus.DISQUALIFIED:
            raise TeamDisqualifiedError()
        elif contest_team.team_status == TeamStatus.CANCELLED:
            raise TeamCanceledError()
