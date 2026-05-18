from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Team
from app.exceptions.student.teams import TeamLeaderAccessDeniedError


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
            raise TeamLeaderAccessDeniedError(team_id=str(team.id), user_id=str(user_id))