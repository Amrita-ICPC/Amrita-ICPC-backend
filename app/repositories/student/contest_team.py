from app.models import Team
from sqlalchemy.orm import selectinload
from app.exceptions.contest import ContestTeamNotFoundException
from sqlalchemy import select
from uuid import UUID
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

    async def get_contest_team_by_id_or_raise(self, contest_team_id: UUID) -> ContestTeam:
        """Get a contest team by its ID or raise an exception if not found.

        Args:
            contest_team_id: The ID of the contest team to retrieve.

        Returns:
            ContestTeam: The contest team with the specified ID.

        Raises:
            ContestTeamNotFoundException: If no contest team is found with the given ID.
        """
        stmt = (
            select(ContestTeam)
            .options(
                selectinload(ContestTeam.team)
                .selectinload(Team.members)
            )
            .where(ContestTeam.id == contest_team_id)
        )
        result = await self.db.execute(stmt)
        contest_team = result.scalar_one_or_none()
        if contest_team is None:
            raise ContestTeamNotFoundException(f"Contest team not found with ID: {contest_team_id}")
        return contest_team

    async def update_contest_team(self, contest_team: ContestTeam) -> ContestTeam:
        """Update an existing contest team record in the database.

        Args:
            contest_team: The ContestTeam model instance to update.

        Returns:
            ContestTeam: The updated and refreshed ContestTeam model instance.
        """
        self.db.add(contest_team)
        await self.db.flush()
        await self.db.refresh(contest_team)
        return contest_team