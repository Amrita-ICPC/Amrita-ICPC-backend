from uuid import UUID

from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.student.teams import (
    TeamLeaderAccessDeniedError,
    TeamMemberAccessDeniedError,
)
from app.models import ContestTeam, Team, TeamUser


class TeamStudentGuard:
    """Guard class for validating student-facing team permission requirements."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the TeamStudentGuard with database connection.

        Args:
            db: Active database session.
        """
        self.db = db

    def check_is_leader(self, user_id: UUID, team: Team) -> None:
        """Check if the requesting student is the leader of the team.

        Args:
            user_id: UUID of the requesting student user.
            team: Team ORM model to check.

        Raises:
            TeamLeaderAccessDeniedError: If the student is not the team leader.
        """
        if team.leader_id != user_id:
            raise TeamLeaderAccessDeniedError(
                team_id=str(team.id), user_id=str(user_id)
            )

    def check_is_contest_team_leader(
        self, user_id: UUID, contest_team: ContestTeam
    ) -> None:
        if contest_team.leader_id != user_id:
            raise TeamLeaderAccessDeniedError(
                team_id=str(contest_team.id), user_id=str(user_id)
            )

    async def check_is_member(self, team_id: UUID, user_id: UUID) -> None:
        query = select(
            exists().where(
                and_(TeamUser.user_id == user_id, TeamUser.team_id == team_id)
            )
        )
        result = await self.db.execute(query)
        is_member = result.scalar()
        if not is_member:
            raise TeamMemberAccessDeniedError(
                team_id=str(team_id), user_id=str(user_id)
            )
