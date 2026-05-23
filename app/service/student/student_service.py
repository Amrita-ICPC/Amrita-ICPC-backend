from typing import List
from uuid import UUID

from sqlalchemy import func, select

from app.mappers.student.student import to_user_invitation_response
from app.models.contest import ContestTeam
from app.repositories.student.contest_team import ContestTeamRepository
from app.schema.user import UserInvitationResponse
from app.utils.enums import (
    ContestTeamMemberStatus,
    TeamApprovalStatus,
    TeamStatus,
)


class StudentService:
    """Service for student-specific operations."""

    def __init__(self, contest_team_repo: ContestTeamRepository) -> None:
        self.contest_team_repo = contest_team_repo

    async def get_user_invitations(
        self, user_id: UUID, status: ContestTeamMemberStatus | None
    ) -> List[UserInvitationResponse]:
        """
        Get all contest invitations for a user.

        Args:
            user_id: The ID of the user.
            status: Optional filter for invitation status.

        Returns:
            A list of user invitation responses.
        """
        invitation = await self.contest_team_repo.get_contest_team_member_by_user_id(
            user_id, status
        )

        if not invitation:
            return []

        contest_team = invitation.contest_team
        contest = contest_team.contest

        registered_teams_count = await self.contest_team_repo.count_teams(
            contest.id, TeamStatus.CONFIRMED, TeamApprovalStatus.APPROVED
        )

        response = to_user_invitation_response(invitation, registered_teams_count)
        if contest_team.team_status != TeamStatus.DRAFT:
            response.can_accept_invitation = False

        return [response]

