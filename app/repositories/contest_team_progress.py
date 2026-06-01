from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.contest import ContestTeamProgressNotFoundError
from app.models.contest import ContestTeamMemberProgress, ContestTeamProgress


class ContestTeamProgressRepository:
    """
    Repository for contest team progress database operations.

    Attributes:
        db: The asynchronous database session.
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize the ContestTeamProgressRepository.

        Args:
            db: The asynchronous database session.
        """
        self.db = db

    async def get_contest_team_progress_by_id(
        self, contest_id: UUID, contest_team_id: UUID, for_update: bool = False
    ) -> ContestTeamProgress | None:
        """
        Fetch a single contest team progress record by contest ID and contest team ID.

        Args:
            contest_id: The UUID of the contest.
            contest_team_id: The UUID of the contest team.
            for_update: If True, acquires a row lock (SELECT ... FOR UPDATE).

        Returns:
            ContestTeamProgress | None: The progress record if found, otherwise None.
        """
        stmt = select(ContestTeamProgress).where(
            ContestTeamProgress.contest_id == contest_id,
            ContestTeamProgress.contest_team_id == contest_team_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        return result.scalars().one_or_none()

    async def get_contest_team_progress_or_raise(
        self, contest_id: UUID, contest_team_id: UUID
    ) -> ContestTeamProgress:
        """
        Retrieve a contest team progress record or raise an exception if not found.

        Args:
            contest_id: The UUID of the contest.
            contest_team_id: The UUID of the contest team.

        Returns:
            ContestTeamProgress: The found progress record.

        Raises:
            ContestTeamProgressNotFoundError: If the progress record does not exist.
        """
        progress = await self.get_contest_team_progress_by_id(
            contest_id, contest_team_id
        )
        if not progress:
            raise ContestTeamProgressNotFoundError(
                str(contest_id), str(contest_team_id)
            )
        return progress

    async def create_contest_team_progress(
        self, progress: ContestTeamProgress
    ) -> ContestTeamProgress:
        """
        Create a new contest team progress record in the database.

        Args:
            progress: The ContestTeamProgress model instance to create.

        Returns:
            ContestTeamProgress: The created progress instance.
        """
        self.db.add(progress)
        await self.db.flush()
        return progress

    async def update_contest_team_progress(
        self, progress: ContestTeamProgress
    ) -> ContestTeamProgress:
        """
        Update an existing contest team progress record.

        Args:
            progress: The ContestTeamProgress model instance to update.

        Returns:
            ContestTeamProgress: The updated progress instance.
        """
        await self.db.flush()
        return progress

    async def get_contest_team_member_progress(
        self, contest_id: UUID, contest_team_id: UUID, contest_team_member_id: UUID
    ) -> ContestTeamMemberProgress | None:
        """
        Fetch a single contest team member progress record by contest ID, team ID and member ID.

        Args:
            contest_id: The UUID of the contest.
            contest_team_id: The UUID of the contest team.
            contest_team_member_id: The UUID of the contest team member.

        Returns:
            ContestTeamMemberProgress | None: The progress record if found, otherwise None.
        """
        stmt = select(ContestTeamMemberProgress).where(
            ContestTeamMemberProgress.contest_id == contest_id,
            ContestTeamMemberProgress.contest_team_id == contest_team_id,
            ContestTeamMemberProgress.contest_team_member_id == contest_team_member_id,
        )
        result = await self.db.execute(stmt)
        return result.scalars().one_or_none()

    async def create_contest_team_member_progress(
        self, member_progress: ContestTeamMemberProgress
    ) -> ContestTeamMemberProgress:
        """
        Create a new contest team member progress record.

        Args:
            member_progress: The ContestTeamMemberProgress model instance to create.

        Returns:
            ContestTeamMemberProgress: The created progress instance.
        """
        self.db.add(member_progress)
        await self.db.flush()
        return member_progress

    async def update_contest_team_member_progress(
        self, member_progress: ContestTeamMemberProgress
    ) -> ContestTeamMemberProgress:
        """
        Update an existing contest team member progress record.

        Args:
            member_progress: The ContestTeamMemberProgress model instance to update.

        Returns:
            ContestTeamMemberProgress: The updated progress instance.
        """
        await self.db.flush()
        return member_progress
