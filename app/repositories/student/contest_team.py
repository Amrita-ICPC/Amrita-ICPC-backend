from app.models import ContestTeamMember
from app.models import ContestTeam
from sqlalchemy.ext.asyncio import AsyncSession
class ContestTeamRepository:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_contest_team(self, contest_team: ContestTeam) -> ContestTeam:
        """Create a new contest team association record in the database.

        Args:
            contest_team: The ContestTeam model instance to save.

        Returns:
            ContestTeam: The persisted and refreshed ContestTeam model instance.
        """
        self.db.add(contest_team)
        await self.db.flush()
        await self.db.refresh(contest_team)
        return contest_team

    async def create_contest_team_members(
        self, contest_team_members: list[ContestTeamMember]
    ) -> list[ContestTeamMember]:
        """Bulk create contest team member records.

        Args:
            contest_team_members: List of ContestTeamMember model instances.

        Returns:
            list[ContestTeamMember]: The list of created ContestTeamMember instances.
        """
        self.db.add_all(contest_team_members)
        await self.db.flush()
        return contest_team_members